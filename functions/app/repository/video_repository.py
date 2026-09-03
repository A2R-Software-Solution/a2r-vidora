from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video_model import Video, VideoStatus


class VideoRepository:
    """Encapsulates all SQL access for the `videos` table."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, video_id: uuid.UUID) -> Video | None:
        result = await self._db.execute(select(Video).where(Video.id == video_id))
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[Video]:
        result = await self._db.execute(
            select(Video).where(Video.user_id == user_id).order_by(Video.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        user_id: uuid.UUID | None,
        youtube_id: str,
        youtube_url: str,
        expires_at: datetime,
    ) -> Video:
        video = Video(
            user_id=user_id,
            youtube_id=youtube_id,
            youtube_url=youtube_url,
            status=VideoStatus.PROCESSING,
            expires_at=expires_at,
        )
        self._db.add(video)
        await self._db.flush()
        await self._db.refresh(video)
        return video

    async def update_metadata(
        self, video: Video, *, title: str | None, duration: int | None
    ) -> Video:
        video.title = title
        video.duration = duration
        await self._db.flush()
        await self._db.refresh(video)
        return video

    async def update_status(self, video: Video, status: VideoStatus) -> Video:
        video.status = status
        await self._db.flush()
        await self._db.refresh(video)
        return video

    async def update_summary(self, video: Video, summary: str) -> Video:
        video.summary = summary
        await self._db.flush()
        await self._db.refresh(video)
        return video

    async def delete(self, video: Video) -> None:
        await self._db.delete(video)
        await self._db.flush()

    async def list_expired(self, *, before: datetime) -> list[Video]:
        result = await self._db.execute(select(Video).where(Video.expires_at < before))
        return list(result.scalars().all())