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
from app.core.logging import logger
from app.models.video_model import Video, VideoStatus
from app.repository.qa_log_repository import QALogRepository
from app.repository.transcript_chunk_repository import TranscriptChunkRepository
from app.repository.video_repository import VideoRepository
from app.schemas.video_schema import VideoCreate
from app.utils.youtube import extract_youtube_id


class VideoNotFoundError(Exception):
    """Raised when a requested video does not exist."""


class VideoExpiredError(Exception):
    """Raised when an operation targets a video past its expires_at."""


class VideoAccessDeniedError(Exception):
    """Raised when a user attempts to access a video they do not own."""


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

    async def mark_failed(self, video: Video) -> Video:
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
        expired_videos = await self._repo.list_expired(before=now)

        for video in expired_videos:
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