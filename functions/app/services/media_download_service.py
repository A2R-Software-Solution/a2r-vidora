import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import delete, select
from app.core.config import settings
from app.integration import media_download_storage
from app.middleware.logging import logger
from app.models.media_download_model import MediaDownload
from app.pipeline.media_download_worker import ACTIVE_STATUSES, FINISHED_STATUSES, stall_window
from app.pipeline.media_downloader import MediaInfo, probe_media
from app.pipeline.media_formats import QUALITIES, get_quality, media_credit_cost
from app.pipeline.youtube_downloader import (
    DownloadError, UnsupportedVideoError, VideoTooLongError, YouTubeBotChallengeError)
from app.services.credit_service import (
    CreditOwner, CreditService, media_download_reservation_key)


def quality_options(duration_seconds: int) -> list[dict]:
    """Every quality with what it would cost for this length of media."""
    return [{
        "code": q.code, "kind": q.kind, "label": q.label, "extension": q.extension,
        "credit_cost": media_credit_cost(q, duration_seconds), "available": q.available,
    } for q in QUALITIES.values()]


async def _probe_or_raise(url: str) -> MediaInfo:
    """Maps yt-dlp failures to HTTP errors the page can show."""
    try:
        return await probe_media(url)
    except (UnsupportedVideoError, VideoTooLongError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except YouTubeBotChallengeError as exc:
        raise HTTPException(503, "YouTube is temporarily blocking downloads. Please try again later.") from exc
    except DownloadError as exc:
        logger.warning("media_probe_failed error=%s", type(exc).__name__)
        raise HTTPException(422, "We could not read this YouTube link.") from exc


class MediaDownloadService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _mine(owner: CreditOwner):
        return MediaDownload.user_id == owner.user_id if owner.user_id else MediaDownload.guest_key == owner.guest_key

    @staticmethod
    def _expire_stalled(jobs):
        cutoff = datetime.now(timezone.utc) - stall_window()
        for job in jobs:
            if job.status in ACTIVE_STATUSES and job.updated_at < cutoff:
                job.status, job.error_code = "failed", "JOB_TIMED_OUT"

    async def preview(self, url: str, owner: CreditOwner) -> dict:
        info = await _probe_or_raise(url)
        summary = await CreditService(self.db).summary(owner)
        return {
            "url": url,
            "title": info.title,
            "thumbnail": info.thumbnail,
            "duration_seconds": info.duration,
            "options": quality_options(info.duration),
            "wallet": {
                "free_left": summary.free_left,
                "purchased_balance": summary.purchased_balance,
                "available": summary.available,
            },
        }

    async def create(self, url: str, quality_code: str, owner: CreditOwner) -> MediaDownload:
        """Prices the media from a fresh probe, then holds the credits and the job
        in one transaction. The caller enqueues the work only when this returns."""
        quality = get_quality(quality_code)
        info = await _probe_or_raise(url)
        cost = media_credit_cost(quality, info.duration)

        download_id, attempt_id = uuid.uuid4(), uuid.uuid4()
        now = datetime.now(timezone.utc)
        credits = CreditService(self.db, commit=False)
        try:
            summary = await credits.summary(owner)  # paid accounts keep results longer
            retention = settings.paid_retention_hours if summary.is_paid else settings.media_download_retention_hours
            job = MediaDownload(
                id=download_id, user_id=owner.user_id, guest_key=owner.guest_key, guest_cap_key=owner.cap_key,
                source_url=url, title=(info.title or "")[:300] or None, quality=quality.code,
                duration_seconds=info.duration, credit_cost=cost, status="queued", attempt_id=attempt_id,
                rights_confirmed_at=now, created_at=now, updated_at=now,
                expires_at=now + timedelta(hours=retention))
            self.db.add(job)
            # Flushed only: committed with the job, or rolled back with it when
            # credits are insufficient (402 from the global handler).
            await credits.reserve(owner, source_type="download", source_id=download_id,
                                  idempotency_key=media_download_reservation_key(download_id, attempt_id),
                                  amount=cost)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(job)
        return job

    async def list(self, owner: CreditOwner, limit: int = 20):
        jobs = list((await self.db.execute(
            select(MediaDownload).where(self._mine(owner))
            .order_by(MediaDownload.created_at.desc()).limit(limit)
        )).scalars())
        self._expire_stalled(jobs)
        await self.db.commit()
        return jobs

    async def get(self, download_id: uuid.UUID, owner: CreditOwner):
        job = (await self.db.execute(
            select(MediaDownload).where(MediaDownload.id == download_id, self._mine(owner)))).scalar_one_or_none()
        if job is None:
            raise HTTPException(404, "Download not found.")
        self._expire_stalled([job])
        await self.db.commit()
        return job

    async def file_link(self, download_id: uuid.UUID, owner: CreditOwner) -> dict:
        job = await self.get(download_id, owner)
        now = datetime.now(timezone.utc)
        if job.expires_at <= now or job.status == "expired":
            raise HTTPException(410, "Download expired.")
        if job.status != "completed" or not job.object_name:
            raise HTTPException(409, "Download is not ready.")
        valid_for = min(600, int((job.expires_at - now).total_seconds()))
        if valid_for < 1:
            raise HTTPException(410, "Download expired.")
        extension = get_quality(job.quality).extension
        filename = f"vidora-{job.id.hex[:8]}.{extension}"
        url = await media_download_storage.signed_url(job.object_name, filename, extension, valid_for=valid_for)
        return {"url": url, "valid_for_seconds": valid_for}

    async def purge_expired(self, *, now: datetime | None = None) -> int:
        """Deletes expired downloads and their stored files. Jobs that may still be
        running are left until they finish or stall."""
        now = now or datetime.now(timezone.utc)
        jobs = list((await self.db.execute(
            select(MediaDownload).where(MediaDownload.expires_at <= now).with_for_update())).scalars())
        purgeable = [j for j in jobs
                     if j.status in FINISHED_STATUSES or j.updated_at < now - stall_window()]
        if settings.media_download_bucket:
            for job in purgeable:
                if job.object_name:
                    try:
                        await media_download_storage.delete(job.object_name)
                    except Exception:
                        logger.exception("media_download_object_delete_failed download_id=%s", job.id)
        if purgeable:
            await self.db.execute(delete(MediaDownload).where(MediaDownload.id.in_([j.id for j in purgeable])))
        await self.db.commit()
        logger.info("Purged %s expired media downloads", len(purgeable))
        return len(purgeable)
