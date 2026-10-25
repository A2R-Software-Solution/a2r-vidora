import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import delete, select
from app.core.config import settings
from app.integration import audio_merge_storage
from app.middleware.logging import logger
from app.models.audio_merge_model import AudioMerge
from app.services.credit_service import (
    CreditOwner, CreditService, audio_merge_credit_cost, audio_merge_reservation_key)

ALLOWED_UPLOAD_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".weba", ".webm", ".mp4"}
ACTIVE_STATUSES = {"queued", "processing"}
FINISHED_STATUSES = {"completed", "failed", "expired"}


def upload_extension(filename: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(415, "Unsupported audio file. Use MP3, WAV, M4A, AAC, OGG, OPUS, FLAC, WEBM or MP4.")
    return extension


def stall_window() -> timedelta:
    # Same grace the cleanup job and credit reconciliation use for dead jobs.
    return timedelta(seconds=settings.audio_merge_timeout_seconds + 1800)


class AudioMergeService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _mine(owner: CreditOwner):
        return AudioMerge.user_id == owner.user_id if owner.user_id else AudioMerge.guest_key == owner.guest_key

    @staticmethod
    def _expire_stalled(jobs):
        cutoff = datetime.now(timezone.utc) - stall_window()
        for job in jobs:
            if job.status in ACTIVE_STATUSES and job.updated_at < cutoff:
                job.status, job.error_code = "failed", "JOB_TIMED_OUT"

    async def create(self, payload, uploads: list[tuple[str, bytes]], owner: CreditOwner):
        """uploads: (extension, content) in the order the request listed its files.
        Credits are reserved in the same transaction as the job; the caller
        enqueues the work only when this returns."""
        upload_tracks = [t for t in payload.tracks if t.source == "upload"]
        if any(t.file_index >= len(uploads) for t in upload_tracks):
            raise HTTPException(422, "A track refers to a file that was not uploaded.")
        if len(uploads) != len(upload_tracks):
            raise HTTPException(422, "Every uploaded file must be used by a track.")

        merge_id, attempt_id = uuid.uuid4(), uuid.uuid4()
        now = datetime.now(timezone.utc)
        tracks, objects = [], []
        for track in payload.tracks:
            entry = {"source": track.source, "start_time": track.start_time, "end_time": track.end_time}
            if track.source == "youtube":
                entry["url"] = track.url
            else:
                extension, content = uploads[track.file_index]
                entry["object_name"] = f"audiomerge/{merge_id}/in-{track.file_index}{extension}"
                objects.append((entry["object_name"], content))
            tracks.append(entry)

        credits = CreditService(self.db, commit=False)
        try:
            summary = await credits.summary(owner)  # paid accounts keep results longer
            retention = settings.paid_retention_hours if summary.is_paid else settings.audio_merge_retention_hours
            cost = audio_merge_credit_cost([t.seconds for t in payload.tracks])
            job = AudioMerge(
                id=merge_id, user_id=owner.user_id, guest_key=owner.guest_key, guest_cap_key=owner.cap_key,
                tracks=tracks, output_format=payload.output_format, crossfade_seconds=payload.crossfade_seconds,
                total_seconds=sum(t.seconds for t in payload.tracks), credit_cost=cost, status="queued",
                attempt_id=attempt_id, created_at=now, updated_at=now,
                expires_at=now + timedelta(hours=retention))
            self.db.add(job)
            # Flushed only: committed with the job, or rolled back with it when
            # credits are insufficient.
            await credits.reserve(owner, source_type="audio_merge", source_id=merge_id,
                                  idempotency_key=audio_merge_reservation_key(merge_id, attempt_id), amount=cost)
        except Exception:
            await self.db.rollback()
            raise
        stored = []
        try:
            for name, content in objects:
                await audio_merge_storage.upload_bytes(name, content)
                stored.append(name)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            await self._delete_objects(stored)
            raise
        await self.db.refresh(job)
        return job

    async def list(self, owner: CreditOwner, limit: int = 20):
        jobs = list((await self.db.execute(
            select(AudioMerge).where(self._mine(owner)).order_by(AudioMerge.created_at.desc()).limit(limit)
        )).scalars())
        self._expire_stalled(jobs)
        await self.db.commit()
        return jobs

    async def get(self, merge_id: uuid.UUID, owner: CreditOwner):
        job = (await self.db.execute(
            select(AudioMerge).where(AudioMerge.id == merge_id, self._mine(owner)))).scalar_one_or_none()
        if job is None:
            raise HTTPException(404, "Merge not found.")
        self._expire_stalled([job])
        await self.db.commit()
        return job

    async def download(self, merge_id: uuid.UUID, owner: CreditOwner, download: bool):
        job = await self.get(merge_id, owner)
        now = datetime.now(timezone.utc)
        if job.expires_at <= now or job.status == "expired":
            raise HTTPException(410, "Merged audio expired.")
        if job.status != "completed" or not job.object_name:
            raise HTTPException(409, "Merged audio is not ready.")
        valid_for = min(600, int((job.expires_at - now).total_seconds()))
        if valid_for < 1:
            raise HTTPException(410, "Merged audio expired.")
        url = await audio_merge_storage.signed_url(job.object_name, job.output_format,
                                                   download=download, valid_for=valid_for)
        return {"url": url, "valid_for_seconds": valid_for}

    async def _delete_objects(self, names):
        for name in names:
            try:
                await audio_merge_storage.delete(name)
            except Exception:
                logger.exception("audio_merge_object_delete_failed object=%s", name)

    async def purge_expired(self, *, now: datetime | None = None) -> int:
        """Deletes expired merges and their stored files. Jobs that may still be
        running are left until they finish or stall."""
        now = now or datetime.now(timezone.utc)
        jobs = list((await self.db.execute(
            select(AudioMerge).where(AudioMerge.expires_at <= now).with_for_update())).scalars())
        purgeable = [j for j in jobs
                     if j.status in FINISHED_STATUSES or j.updated_at < now - stall_window()]
        if settings.audio_merge_bucket:
            for job in purgeable:
                names = [t["object_name"] for t in job.tracks if t.get("object_name")]
                if job.object_name:
                    names.append(job.object_name)
                await self._delete_objects(names)
        if purgeable:
            await self.db.execute(delete(AudioMerge).where(AudioMerge.id.in_([j.id for j in purgeable])))
        await self.db.commit()
        logger.info("Purged %s expired audio merges", len(purgeable))
        return len(purgeable)
