import uuid

from fastapi import Request, Response, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.logging import logger
from app.core.config import settings
from app.core.recaptcha import verify_recaptcha
from app.deps import get_db
from app.core.rate_limit import rate_limit_user
from app.schemas.video_schema import VideoCreate, VideoResponse
from app.services.video_service import (
    VideoAccessDeniedError,
    VideoExpiredError,
    VideoNotFoundError,
    VideoService,
    SubmissionConflictError,
)
from app.models.video_model import VideoStatus
from app.integration.video_tasks import enqueue_video_processing


async def _enqueue_video_processing(video_id: uuid.UUID, youtube_url: str) -> None:
    await enqueue_video_processing(video_id, youtube_url)


async def submit_video(
    payload: VideoCreate,
    idempotency_key: uuid.UUID | None = Header(default=None),
    recaptcha_token: str | None = Header(default=None, alias="X-Recaptcha-Token"),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(rate_limit_user),
    *, request: Request, response: Response,
) -> VideoResponse:
    if not settings.ai_enabled:
        raise HTTPException(status_code=503, detail="AI processing is temporarily paused.")
    await verify_recaptcha(recaptcha_token, expected_action="analyze_video")
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
        await _enqueue_video_processing(video.id, video.youtube_url)
    except Exception as exc:
        # The row has already been committed. Do not leave a job that cannot
        # be dispatched indefinitely in PROCESSING.
        logger.exception("video_enqueue_failed video_id=%s", video.id)
        await service.mark_failed(video)
        raise HTTPException(status_code=503, detail="Video processing queue is temporarily unavailable.") from exc

    # Return promptly; clients poll GET /videos?video_id=... for status.
    return VideoResponse.model_validate(video)


async def list_videos(
    video_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(rate_limit_user),
    *, request: Request, response: Response,
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
