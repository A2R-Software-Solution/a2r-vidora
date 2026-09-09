import asyncio
import uuid

from fastapi import Depends, Header, HTTPException, Query, status
from firebase_admin import functions as admin_functions
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.config import settings
from app.core.rate_limit import enforce_submit_rate_limit
from app.deps import get_current_user_id, get_db
from app.schemas.video_schema import VideoCreate, VideoResponse
from app.pipeline.pipeline import PipelineError, run_pipeline
from app.services.video_service import (
    VideoAccessDeniedError,
    VideoExpiredError,
    VideoNotFoundError,
    VideoService,
    SubmissionConflictError,
)
from app.models.video_model import VideoStatus


_VIDEO_PROCESSING_TASK = "processvideo"


async def _enqueue_video_processing(video_id: uuid.UUID, youtube_url: str) -> None:
    queue = admin_functions.task_queue(_VIDEO_PROCESSING_TASK)
    options = admin_functions.TaskOptions(
        dispatch_deadline_seconds=300,
        task_id=f"video-{video_id.hex}",
    )
    await asyncio.to_thread(
        queue.enqueue,
        # The Python Admin SDK serializes this body as-is; the Firebase task
        # handler requires the callable protocol's top-level data envelope.
        {"data": {"video_id": str(video_id), "youtube_url": youtube_url}},
        options,
    )


async def submit_video(
    payload: VideoCreate,
    idempotency_key: uuid.UUID | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(get_current_user_id),
    _rate_limit: None = Depends(enforce_submit_rate_limit),
) -> VideoResponse:
    if not settings.ai_enabled:
        raise HTTPException(status_code=503, detail="AI processing is temporarily paused.")
    service = VideoService(db)
    try:
        video, created = await service.submit_once(
            payload, user_id=user_id, request_id=idempotency_key or uuid.uuid4(),
        )
    except (SubmissionConflictError, VideoAccessDeniedError, VideoExpiredError) as exc:
        raise HTTPException(status_code=409, detail="Submission identifier is unavailable.") from exc
    if not created:
        if video.status == VideoStatus.COMPLETED:
            return VideoResponse.model_validate(video)
        if video.status == VideoStatus.FAILED:
            # The browser may safely discard this idempotency key and create a
            # new job only after an explicit subsequent user action.
            raise HTTPException(
                status_code=409,
                detail="This submission previously failed. You can submit it again.",
            )
        raise HTTPException(
            status_code=409,
            detail="This submission is still processing. Check its result again later.",
        )

    try:
        async with asyncio.timeout(270):
            video = await run_pipeline(video.id, video.youtube_url, db=db)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Analysis exceeded the processing time limit. Please try a shorter video.",
        ) from exc
    except PipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Video processing failed. Please try again later with a supported video up to 35 minutes.",
        ) from exc

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
