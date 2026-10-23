"""
services/video_service.py

Business logic for the Video entity.

Responsibility: orchestrates the VideoRepository, applies business rules
(ownership, expiry, retention window), and owns the transaction boundary
for operations it exposes. Routes call this layer only.

Note: the actual yt-dlp / STT / embedding pipeline is intentionally NOT
here — that belongs in a separate ingestion/pipeline module that this
service will call into once it exists. This file only covers the CRUD-
adjacent business logic around a video record itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.middleware.logging import logger
from app.models.video_model import Video, VideoStatus
from app.repository.qa_log_repository import QALogRepository
from app.repository.transcript_chunk_repository import TranscriptChunkRepository
from app.models.transcript_chunk_model import TranscriptChunk
from app.repository.video_repository import VideoRepository
from app.schemas.video_schema import VideoCreate
from app.utils.youtube import extract_youtube_id
from app.models.short_model import Short
from app.integration import short_storage
from app.services.credit_service import CreditOwner, CreditService, video_credit_cost
from sqlalchemy import select


class VideoNotFoundError(Exception):
    """Raised when a requested video does not exist."""


class VideoExpiredError(Exception):
    """Raised when an operation targets a video past its expires_at."""


class VideoAccessDeniedError(Exception):
    """Raised when a user attempts to access a video they do not own."""


class SubmissionConflictError(Exception):
    """An idempotency key was reused for a different submission."""


class VideoService:
    """Business logic layer for video submission and lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = VideoRepository(db)
        self._chunk_repo = TranscriptChunkRepository(db)
        self._qa_log_repo = QALogRepository(db)

    async def submit(
        self, payload: VideoCreate, *, user_id: uuid.UUID | None
    ) -> Video:
        """
        Creates a new video record in PROCESSING state. The caller
        (ingestion pipeline, triggered separately) is responsible for
        later filling in title/duration and moving status forward.
        """
        youtube_id = extract_youtube_id(payload.youtube_url)

        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=settings.video_retention_hours
        )

        video = await self._repo.create(
            user_id=user_id,
            youtube_id=youtube_id,
            youtube_url=payload.youtube_url,
            expires_at=expires_at,
        )
        await self._db.commit()
        return video

    async def get_for_user(
        self, video_id: uuid.UUID, *, user_id: uuid.UUID | None
    ) -> Video:
        """
        Fetches a video, enforcing ownership when the video has an
        owner. Anonymous videos (user_id is None on the row) are
        readable by anyone holding the video_id, per MVP scope.
        """
        video = await self._repo.get_by_id(video_id)
        if video is None:
            raise VideoNotFoundError(f"Video {video_id} not found.")

        if self._is_expired(video):
            raise VideoExpiredError(f"Video {video_id} has expired.")

        if video.user_id is not None and video.user_id != user_id:
            raise VideoAccessDeniedError(
                f"User {user_id} does not own video {video_id}."
            )

        # Only on an explicit read/retry: no scheduled polling invocations.
        # New submissions start immediately and have a 300-second platform cap.
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.stale_processing_seconds)
        if (video.status == VideoStatus.PROCESSING
                and video.processing_stage != "waiting_for_quota"
                and video.processing_updated_at < cutoff):
            await self._repo.fail_stale(video_id, cutoff)
            await self._db.commit()
            await self._db.refresh(video)
        return video

    async def submit_once(self, payload: VideoCreate, *, user_id: uuid.UUID | None,
                          request_id: uuid.UUID,
                          owner: CreditOwner | None = None) -> tuple[Video, bool]:
        """owner is the wallet to charge; None skips credits (internal callers)."""
        youtube_id = extract_youtube_id(payload.youtube_url)
        existing = await self._repo.get_by_id(request_id)
        if existing is not None:
            if existing.user_id != user_id or existing.youtube_id != youtube_id:
                raise SubmissionConflictError("Request identifier already used for another submission.")
            return existing, False

        now = datetime.now(timezone.utc)
        guest_key = owner.guest_key if owner is not None else None
        guest_cap_key = owner.cap_key if owner is not None else None
        reusable = await self._repo.find_reusable_completed(youtube_id, now=now)
        if reusable is not None:
            priority = False
            if owner is not None:
                # The result is delivered now, so the charge is final now. Not
                # committed until the copy below is, so they succeed together.
                credits = CreditService(self._db, commit=False)
                priority = (await credits.summary(owner)).is_paid
                hold = await credits.reserve_video(owner, request_id, video_credit_cost(reusable.duration or 1))
                await credits.settle(hold.id)
            # Free copies never outlive their source; a paid copy owns its
            # chunks (copied below), so it keeps the full paid retention.
            expires_at = (now + timedelta(hours=settings.paid_retention_hours) if priority
                          else min(reusable.expires_at, now + timedelta(hours=settings.video_retention_hours)))
            # A requester gets their own record, Q&A history and Shorts quota.
            # Transcript chunks are copied so source cleanup cannot affect it.
            video = Video(
                id=request_id,
                user_id=user_id,
                guest_key=guest_key,
                guest_cap_key=guest_cap_key,
                youtube_id=youtube_id,
                youtube_url=f"https://www.youtube.com/watch?v={youtube_id}",
                title=reusable.title,
                duration=reusable.duration,
                status=VideoStatus.COMPLETED,
                summary=reusable.summary,
                processing_stage="completed",
                processing_total_chunks=reusable.processing_total_chunks,
                processing_completed_chunks=reusable.processing_completed_chunks,
                priority=priority,
                expires_at=expires_at,
            )
            self._db.add(video)
            source_chunks = await self._chunk_repo.list_by_video(reusable.id)
            self._db.add_all([
                TranscriptChunk(
                    video_id=video.id,
                    chunk_text=chunk.chunk_text,
                    start_time=chunk.start_time,
                    end_time=chunk.end_time,
                    embedding=chunk.embedding,
                )
                for chunk in source_chunks
            ])
            await self._db.commit()
            await self._db.refresh(video)
            logger.info("analysis_reused video_id=%s source_video_id=%s", video.id, reusable.id)
            return video, False

        priority = False
        if owner is not None:
            # The cost is known only after the worker reads the duration; it
            # reserves then. Here we only refuse when nothing is left at all.
            priority = (await CreditService(self._db).ensure_available(owner)).is_paid
        retention = settings.paid_retention_hours if priority else settings.video_retention_hours
        created = await self._repo.create_once(
            request_id, user_id=user_id, guest_key=guest_key, guest_cap_key=guest_cap_key,
            priority=priority, youtube_id=youtube_id,
            youtube_url=f"https://www.youtube.com/watch?v={youtube_id}",
            expires_at=now + timedelta(hours=retention),
        )
        await self._db.commit()
        video = await self.get_for_user(request_id, user_id=user_id)
        if video.user_id != user_id or video.youtube_id != youtube_id:
            raise SubmissionConflictError("Request identifier already used for another submission.")
        return video, created

    async def get_for_processing(self, video_id: uuid.UUID) -> Video:
        """Fetch a queued video without applying end-user ownership checks."""
        video = await self._repo.get_by_id(video_id)
        if video is None:
            raise VideoNotFoundError(f"Video {video_id} not found.")
        if self._is_expired(video):
            raise VideoExpiredError("Video expired.")
        return video

    async def list_for_user(self, user_id: uuid.UUID) -> list[Video]:
        return await self._repo.list_by_user(user_id)

    async def mark_metadata(
        self, video: Video, *, title: str | None, duration: int | None
    ) -> Video:
        updated = await self._repo.update_metadata(
            video, title=title, duration=duration
        )
        await self._db.commit()
        return updated

    async def mark_completed(self, video: Video, *, summary: str) -> Video:
        video = await self._repo.update_status(video, VideoStatus.COMPLETED)
        video = await self._repo.update_summary(video, summary)
        await self._db.commit()
        return video

    async def mark_progress(self, video: Video, *, stage: str, total_chunks: int | None = None,
                            completed_chunks: int | None = None) -> Video:
        video = await self._repo.update_progress(video, stage=stage, total_chunks=total_chunks,
                                                 completed_chunks=completed_chunks)
        await self._db.commit()
        return video

    async def mark_failed(self, video: Video, *, reason: str | None = None) -> Video:
        if reason is not None:
            video = await self._repo.update_progress(video, stage=reason)
        updated = await self._repo.update_status(video, VideoStatus.FAILED)
        await self._db.commit()
        return updated

    async def purge_expired(self, *, now: datetime | None = None) -> int:
        """
        Deletes every video past its expires_at, along with its
        transcript_chunks and qa_logs. No DB-level ON DELETE CASCADE
        is set up, so child rows are deleted explicitly, in FK order,
        before the video row itself. Returns the number of videos purged.
        """
        now = now or datetime.now(timezone.utc)
        expired_shorts = list((await self._db.execute(
            select(Short).where(Short.expires_at <= now).with_for_update()
        )).scalars())
        for short in expired_shorts:
            if short.object_name:
                await short_storage.delete(short.object_name)
                short.object_name = None
            short.status = "expired"
        await self._db.flush()
        expired_videos = await self._repo.list_expired(before=now)

        for video in expired_videos:
            # Keep expired job records until the parent expires so cleanup
            # never restores the two-success allowance for a live analysis.
            from sqlalchemy import delete
            await self._db.execute(delete(Short).where(Short.video_id == video.id))
            await self._chunk_repo.delete_by_video(video.id)
            await self._qa_log_repo.delete_by_video(video.id)
            await self._repo.delete(video)

        await self._db.commit()
        logger.info(f"Purged {len(expired_videos)} expired videos")
        return len(expired_videos)

    def ensure_ready_for_qa(self, video: Video) -> None:
        """
        Business rule: Q&A is only allowed once processing has
        completed. Raises rather than returning a bool so the caller
        cannot accidentally ignore the check.
        """
        if self._is_expired(video):
            raise VideoExpiredError(f"Video {video.id} has expired.")
        if video.status != VideoStatus.COMPLETED:
            raise VideoNotFoundError(
                f"Video {video.id} is not ready for Q&A (status={video.status.value})."
            )

    @staticmethod
    def _is_expired(video: Video) -> bool:
        return video.expires_at <= datetime.now(timezone.utc)
