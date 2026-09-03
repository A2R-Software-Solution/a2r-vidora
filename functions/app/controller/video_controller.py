from fastapi import BackgroundTasks, Depends, HTTPException, Query, status
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.rate_limit import enforce_submit_rate_limit
from app.db.session import AsyncSessionLocal
from app.deps import get_current_user_id, get_db
from app.pipeline.pipeline import PipelineError, run_pipeline
from app.schemas.video_schema import VideoCreate, VideoResponse
from app.services.video_service import (
    VideoAccessDeniedError,
    VideoExpiredError,
    VideoNotFoundError,
    VideoService,
)


async def _run_pipeline_background(video_id: uuid.UUID, youtube_url: str) -> None:
    async with AsyncSessionLocal() as db:
        try:
            await run_pipeline(video_id, youtube_url, db=db)
        except PipelineError:
            logger.error(f"Background pipeline run failed for video {video_id}")


async def submit_video(
    payload: VideoCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(get_current_user_id),
    _rate_limit: None = Depends(enforce_submit_rate_limit),
) -> VideoResponse:
    service = VideoService(db)
    video = await service.submit(payload, user_id=user_id)

    background_tasks.add_task(_run_pipeline_background, video.id, payload.youtube_url)

    return VideoResponse.model_validate(video)


async def list_videos(
    video_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> list[VideoResponse]:
    service = VideoService(db)

    if video_id is not None:
        try:
            video = await service.get_for_user(video_id, user_id=user_id)
        except VideoNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except VideoExpiredError as exc:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
        except VideoAccessDeniedError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return [VideoResponse.model_validate(video)]

    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    videos = await service.list_for_user(user_id)
    return [VideoResponse.model_validate(v) for v in videos]