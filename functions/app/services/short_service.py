import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from fastapi import HTTPException
from app.core.config import settings
from app.models.video_model import Video
from app.models.short_model import Short
from app.services.video_service import VideoService
from app.integration import short_storage
from app.repository.transcript_chunk_repository import TranscriptChunkRepository
from app.services.credit_service import CreditOwner, CreditService, short_reservation_key


class ShortService:
    def __init__(self, db):
        self.db = db

    async def _video(self, video_id, user_id):
        return await VideoService(self.db).get_for_user(video_id, user_id=user_id)

    async def list(self, video_id, user_id):
        await self._video(video_id, user_id)
        await self.db.execute(select(Video.id).where(Video.id == video_id).with_for_update())
        jobs = list((await self.db.execute(select(Short).where(Short.video_id == video_id).order_by(Short.created_at).with_for_update())).scalars())
        self._expire_stalled(jobs)
        await self.db.commit()
        return jobs

    @staticmethod
    def _expire_stalled(jobs):
        now = datetime.now(timezone.utc)
        for job in jobs:
            if job.status in {"queued", "rendering"} and job.updated_at < now - timedelta(seconds=settings.shorts_timeout_seconds + 1800):
                job.status, job.error_code = "failed", "JOB_TIMED_OUT"

    async def create(self, video_id, payload, user_id, owner: CreditOwner | None = None):
        """owner is the wallet charged per render attempt; None skips credits."""
        video = await self._video(video_id, user_id)
        VideoService(self.db).ensure_ready_for_qa(video)
        if not video.duration or payload.end_time > video.duration:
            raise HTTPException(422, "Clip exceeds the video duration.")
        chunks = await TranscriptChunkRepository(self.db).find_in_time_range(video_id, payload.start_time, payload.end_time)
        if not any(chunk.chunk_text.strip() for chunk in chunks):
            raise HTTPException(422, "This range has no transcript for captions.")
        # Serialize reservations across API instances, including duplicate clicks.
        await self.db.execute(select(Video.id).where(Video.id == video_id).with_for_update())
        jobs = list((await self.db.execute(select(Short).where(Short.video_id == video_id).with_for_update())).scalars())
        now = datetime.now(timezone.utc)
        self._expire_stalled(jobs)
        existing = next((j for j in jobs if j.start_time == payload.start_time and j.end_time == payload.end_time), None)
        if existing and existing.status != "failed":
            await self.db.commit()
            return existing, False
        # A paid video's Shorts share its paid retention.
        retention = (settings.paid_retention_hours if getattr(video, "priority", False)
                     else settings.shorts_retention_hours)
        expires = min(video.expires_at, now + timedelta(hours=retention))
        if existing:
            job = existing
            job.status, job.error_code, job.attempt_id = "queued", None, uuid.uuid4()
            job.updated_at, job.expires_at = now, expires
        else:
            job = Short(id=uuid.uuid4(), video_id=video_id, start_time=payload.start_time,
                        end_time=payload.end_time, status="queued", expires_at=expires,
                        updated_at=now, attempt_id=uuid.uuid4())
            self.db.add(job)
        if owner is not None:
            # Flushed only: committed together with the job, or rolled back with
            # it when credits are insufficient.
            await CreditService(self.db, commit=False).reserve(
                owner, source_type="short", source_id=job.id,
                idempotency_key=short_reservation_key(job.id, job.attempt_id),
                amount=settings.short_credit_cost)
        await self.db.commit()
        await self.db.refresh(job)
        return job, True

    async def get(self, video_id, short_id, user_id):
        jobs = await self.list(video_id, user_id)
        job = next((item for item in jobs if item.id == short_id), None)
        if job is None:
            raise HTTPException(404, "Short not found.")
        return job

    async def download(self, video_id, short_id, user_id, download):
        job = await self.get(video_id, short_id, user_id)
        if job.expires_at <= datetime.now(timezone.utc) or job.status == "expired":
            raise HTTPException(410, "Short expired.")
        if job.status != "completed" or not job.object_name:
            raise HTTPException(409, "Short is not ready.")
        valid_for = min(600, int((job.expires_at - datetime.now(timezone.utc)).total_seconds()))
        if valid_for < 1:
            raise HTTPException(410, "Short expired.")
        return {"url": await short_storage.signed_url(job.object_name, download=download, valid_for=valid_for), "valid_for_seconds": valid_for}
