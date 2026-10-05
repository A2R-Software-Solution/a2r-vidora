import asyncio
import uuid
from fastapi import Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from firebase_admin import functions as admin_functions
from app.core.config import settings
from app.core.rate_limit import limiter, rate_limit_user
from app.deps import get_db
from app.models.short_model import Short
from app.schemas.short_schema import ShortRequest, ShortResponse
from app.services.short_service import ShortService
from app.services.video_service import VideoAccessDeniedError, VideoExpiredError, VideoNotFoundError
from app.utils.router_config import create_router

router = create_router(prefix="/videos/{video_id}/shorts", tags=["Shorts"])


async def _handle(operation):
    try:
        return await operation
    except VideoAccessDeniedError as exc:
        raise HTTPException(403, "Video access denied.") from exc
    except VideoExpiredError as exc:
        raise HTTPException(410, "Video expired.") from exc
    except VideoNotFoundError as exc:
        raise HTTPException(404, "Video not found.") from exc


@router.post("", response_model=ShortResponse, status_code=202)
@limiter.limit("10/hour")
async def create_short(video_id: uuid.UUID, payload: ShortRequest, request: Request, response: Response,
                       db=Depends(get_db), user_id=Depends(rate_limit_user)):
    if not settings.ai_enabled or not settings.shorts_enabled or not settings.shorts_bucket:
        raise HTTPException(503, "Short creation is not available yet.")
    job, created = await _handle(ShortService(db).create(video_id, payload, user_id))
    if created:
        try:
            queue = admin_functions.task_queue(settings.shorts_processing_task)
            await asyncio.to_thread(queue.enqueue,
                {"data": {"short_id": str(job.id), "attempt_id": str(job.attempt_id)}},
                admin_functions.TaskOptions(dispatch_deadline_seconds=settings.shorts_timeout_seconds + 120,
                    task_id=f"short-{job.id.hex}-{job.attempt_id.hex}"))
        except Exception as exc:
            # Preserve a worker claim if dispatch succeeded but acknowledgement was lost.
            attempt = job.attempt_id
            await db.refresh(job)
            locked = (await db.execute(select(Short).where(Short.id == job.id).with_for_update())).scalar_one()
            if locked.attempt_id == attempt and locked.status == "queued":
                locked.status, locked.error_code = "failed", "QUEUE_UNAVAILABLE"
                await db.commit()
            raise HTTPException(503, "Short creation queue is unavailable. Please retry.") from exc
    return job


@router.get("")
@limiter.limit("50/minute")
async def list_shorts(video_id: uuid.UUID, request: Request, response: Response,
                      db=Depends(get_db), user_id=Depends(rate_limit_user)):
    jobs = await _handle(ShortService(db).list(video_id, user_id))
    return {"items": [ShortResponse.model_validate(job) for job in jobs], "free_limit": 2,
            "used": sum(job.status != "failed" for job in jobs)}


@router.get("/{short_id}", response_model=ShortResponse)
@limiter.limit("50/minute")
async def get_short(video_id: uuid.UUID, short_id: uuid.UUID, request: Request, response: Response,
                    db=Depends(get_db), user_id=Depends(rate_limit_user)):
    return await _handle(ShortService(db).get(video_id, short_id, user_id))


@router.get("/{short_id}/download")
@limiter.limit("20/minute")
async def download_short(video_id: uuid.UUID, short_id: uuid.UUID, request: Request, response: Response,
                         download: bool = Query(True), db=Depends(get_db), user_id=Depends(rate_limit_user)):
    return await _handle(ShortService(db).download(video_id, short_id, user_id, download))
