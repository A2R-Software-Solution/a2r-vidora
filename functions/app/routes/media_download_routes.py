import asyncio
import uuid
from fastapi import Depends, HTTPException, Request, Response
from firebase_admin import functions as admin_functions
from sqlalchemy import select
from app.core.config import settings
from app.core.rate_limit import credit_owner_for, limiter, rate_limit_user
from app.deps import get_db
from app.models.media_download_model import MediaDownload
from app.pipeline.media_formats import QUALITIES
from app.schemas.media_download_schema import DownloadRequest, DownloadResponse, PreviewRequest
from app.services.credit_service import CreditService, media_download_reservation_key
from app.services.media_download_service import MediaDownloadService
from app.utils.router_config import create_router

router = create_router(prefix="/downloads", tags=["Media Downloader"])


def _ensure_enabled():
    if not settings.media_download_enabled or not settings.media_download_bucket:
        raise HTTPException(503, "The Media Downloader is not available yet.")


@router.get("/limits")
@limiter.limit("60/minute")
async def download_limits(request: Request, response: Response):
    """What the page needs to show the qualities and their per-minute prices."""
    return {
        "enabled": settings.media_download_enabled and bool(settings.media_download_bucket),
        "max_seconds": settings.media_download_max_seconds,
        "qualities": [{
            "code": q.code, "kind": q.kind, "label": q.label,
            "credits_per_minute": q.credits_per_minute, "extension": q.extension,
            "available": q.available,
        } for q in QUALITIES.values()],
    }


@router.post("/preview")
@limiter.limit("20/minute")
async def preview_download(request: Request, response: Response, payload: PreviewRequest,
                           db=Depends(get_db), user_id=Depends(rate_limit_user)):
    """Title, length and the price of every quality. Charges nothing."""
    _ensure_enabled()
    return await MediaDownloadService(db).preview(payload.url, credit_owner_for(request, user_id))


@router.post("", response_model=DownloadResponse, status_code=202)
@limiter.limit("10/hour")
async def create_download(request: Request, response: Response, payload: DownloadRequest,
                          db=Depends(get_db), user_id=Depends(rate_limit_user)):
    _ensure_enabled()
    job = await MediaDownloadService(db).create(payload.url, payload.quality, credit_owner_for(request, user_id))
    try:
        queue = admin_functions.task_queue(settings.media_download_processing_task)
        await asyncio.to_thread(queue.enqueue,
            {"data": {"download_id": str(job.id), "attempt_id": str(job.attempt_id)}},
            admin_functions.TaskOptions(dispatch_deadline_seconds=settings.media_download_timeout_seconds + 120,
                task_id=f"download-{job.id.hex}-{job.attempt_id.hex}"))
    except Exception as exc:
        # Same handling as Song Merger: only fail the job if no worker claimed it.
        attempt = job.attempt_id
        await db.refresh(job)
        locked = (await db.execute(
            select(MediaDownload).where(MediaDownload.id == job.id).with_for_update())).scalar_one()
        if locked.attempt_id == attempt and locked.status == "queued":
            locked.status, locked.error_code = "failed", "QUEUE_UNAVAILABLE"
            await db.commit()
            credits = CreditService(db)
            hold = await credits.reservation_id(media_download_reservation_key(job.id, attempt))
            if hold is not None:
                await credits.finish_failed(hold, reason="QUEUE_UNAVAILABLE")
        raise HTTPException(503, "The download queue is unavailable. Please retry.") from exc
    return DownloadResponse.from_job(job)


@router.get("")
@limiter.limit("50/minute")
async def list_downloads(request: Request, response: Response, db=Depends(get_db),
                         user_id=Depends(rate_limit_user)):
    jobs = await MediaDownloadService(db).list(credit_owner_for(request, user_id))
    return {"items": [DownloadResponse.from_job(job) for job in jobs]}


@router.get("/{download_id}", response_model=DownloadResponse)
@limiter.limit("120/minute")
async def get_download(download_id: uuid.UUID, request: Request, response: Response,
                       db=Depends(get_db), user_id=Depends(rate_limit_user)):
    job = await MediaDownloadService(db).get(download_id, credit_owner_for(request, user_id))
    return DownloadResponse.from_job(job)


@router.get("/{download_id}/file")
@limiter.limit("20/minute")
async def download_file(download_id: uuid.UUID, request: Request, response: Response,
                        db=Depends(get_db), user_id=Depends(rate_limit_user)):
    return await MediaDownloadService(db).file_link(download_id, credit_owner_for(request, user_id))
