import asyncio
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.integration import media_download_storage
from app.middleware.logging import logger
from app.models.media_download_model import MediaDownload
from app.pipeline.media_downloader import download_media
from app.pipeline.media_formats import get_quality
from app.pipeline.youtube_downloader import (
    UnsupportedVideoError, VideoTooLongError, YouTubeBotChallengeError)
from app.services.credit_service import CreditService, media_download_reservation_key

ACTIVE_STATUSES = {"queued", "processing"}
FINISHED_STATUSES = {"completed", "failed", "expired"}


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, YouTubeBotChallengeError):
        return "YOUTUBE_BLOCKED"
    if isinstance(exc, (UnsupportedVideoError, VideoTooLongError)):
        return "UNSUPPORTED_MEDIA"
    return "DOWNLOAD_FAILED"


def stall_window() -> timedelta:
    # Same grace the cleanup job and credit reconciliation use for dead jobs.
    return timedelta(seconds=settings.media_download_timeout_seconds + 1800)


async def _finish_credits(download_id, attempt_id, *, succeeded: bool, reason: str | None = None) -> None:
    """Settles or refunds this attempt's hold. A failure here is only logged:
    the cleanup job reconciles any hold left open."""
    try:
        async with AsyncSessionLocal() as db:
            credits = CreditService(db)
            hold = await credits.reservation_id(media_download_reservation_key(download_id, attempt_id))
            if hold is None:
                return
            if succeeded:
                await credits.settle(hold)
            else:
                await credits.finish_failed(hold, reason=reason)
    except Exception:
        logger.exception("media_download_credit_finish_failed download_id=%s", download_id)


async def _fail(download_id, attempt_id, code):
    async with AsyncSessionLocal() as db:
        job = (await db.execute(
            select(MediaDownload).where(MediaDownload.id == download_id).with_for_update())).scalar_one_or_none()
        if job and job.attempt_id == attempt_id and job.status == "processing":
            job.status, job.error_code = "failed", code
            job.updated_at = datetime.now(timezone.utc)
            await db.commit()
    await _finish_credits(download_id, attempt_id, succeeded=False, reason=code)


async def process_media_download(download_id, attempt_id):
    download_id, attempt_id = uuid.UUID(download_id), uuid.UUID(attempt_id)
    async with AsyncSessionLocal() as db:
        job = (await db.execute(
            select(MediaDownload).where(MediaDownload.id == download_id).with_for_update())).scalar_one_or_none()
        if not job or job.attempt_id != attempt_id or job.status != "queued":
            return
        if job.expires_at <= datetime.now(timezone.utc):
            job.status = "expired"
            await db.commit()
            await _finish_credits(download_id, attempt_id, succeeded=False, reason="expired")
            return
        job.status, job.updated_at = "processing", datetime.now(timezone.utc)
        source_url, quality_code = job.source_url, job.quality
        await db.commit()

    quality = get_quality(quality_code)
    object_name = f"downloads/{download_id}/{attempt_id}.{quality.extension}"
    try:
        with tempfile.TemporaryDirectory(prefix="vidora_download_") as directory:
            media = await download_media(source_url, output_dir=directory, quality=quality)
            await media_download_storage.upload(object_name, media.path, quality.extension)
        async with AsyncSessionLocal() as db:
            job = (await db.execute(
                select(MediaDownload).where(MediaDownload.id == download_id).with_for_update())).scalar_one_or_none()
            if (not job or job.attempt_id != attempt_id or job.status != "processing"
                    or job.expires_at <= datetime.now(timezone.utc)):
                await media_download_storage.delete(object_name)
                return
            job.status, job.object_name, job.updated_at = "completed", object_name, datetime.now(timezone.utc)
            if media.title and not job.title:
                job.title = media.title[:300]
            await db.commit()
        await _finish_credits(download_id, attempt_id, succeeded=True)
    except Exception as exc:
        logger.exception("media_download_failed download_id=%s", download_id)
        try:
            await media_download_storage.delete(object_name)
        except Exception:
            logger.exception("media_download_upload_cleanup_failed download_id=%s", download_id)
        await _fail(download_id, attempt_id, _failure_code(exc))
