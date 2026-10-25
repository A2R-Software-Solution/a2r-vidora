import asyncio
import json
import uuid
from fastapi import Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from firebase_admin import functions as admin_functions
from app.core.config import settings
from app.core.rate_limit import credit_owner_for, limiter, rate_limit_user
from app.deps import get_db
from app.models.audio_merge_model import AudioMerge
from app.schemas.audio_merge_schema import AudioMergeRequest, AudioMergeResponse
from app.services.audio_merge_service import AudioMergeService, upload_extension
from app.services.credit_service import CreditService, audio_merge_reservation_key
from app.utils.router_config import create_router

router = create_router(prefix="/audio-merges", tags=["Song Merger"])

# Multipart framing around the files themselves.
REQUEST_OVERHEAD_BYTES = 64 * 1024


def _ensure_enabled():
    if not settings.audio_merge_enabled or not settings.audio_merge_bucket:
        raise HTTPException(503, "Song Merger is not available yet.")


async def _read_uploads(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    uploads, total = [], 0
    limit = settings.audio_merge_max_upload_bytes
    for file in files:
        extension = upload_extension(file.filename)
        content = await file.read(limit + 1)
        if len(content) > limit:
            raise HTTPException(413, f"Each file can be at most {limit // (1024 * 1024)} MB.")
        if not content:
            raise HTTPException(422, "An uploaded file is empty.")
        total += len(content)
        if total > settings.audio_merge_max_request_bytes:
            raise HTTPException(413, "The uploaded files are too large in total.")
        uploads.append((extension, content))
    return uploads


@router.get("/limits")
@limiter.limit("60/minute")
async def merge_limits(request: Request, response: Response):
    """What the UI needs to validate input and show the price before submitting."""
    return {
        "enabled": settings.audio_merge_enabled and bool(settings.audio_merge_bucket),
        "max_tracks": settings.audio_merge_max_tracks,
        "max_segment_seconds": settings.audio_merge_max_segment_seconds,
        "max_total_seconds": settings.audio_merge_max_total_seconds,
        "max_upload_bytes": settings.audio_merge_max_upload_bytes,
        "max_request_bytes": settings.audio_merge_max_request_bytes,
        "extra_track_credits": settings.audio_merge_extra_track_credits,
        "max_crossfade_seconds": 10,
        "output_formats": ["mp3", "m4a"],
    }


@router.post("", response_model=AudioMergeResponse, status_code=202)
@limiter.limit("10/hour")
async def create_merge(request: Request, response: Response, spec: str = Form(...),
                       files: list[UploadFile] = File(default=[]),
                       db=Depends(get_db), user_id=Depends(rate_limit_user)):
    _ensure_enabled()
    try:
        payload = AudioMergeRequest.model_validate(json.loads(spec))
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "spec must be valid JSON.") from exc
    except ValidationError as exc:
        raise HTTPException(422, json.loads(exc.json(include_url=False, include_context=False))) from exc
    uploads = await _read_uploads(files)
    owner = credit_owner_for(request, user_id)
    job = await AudioMergeService(db).create(payload, uploads, owner)
    try:
        queue = admin_functions.task_queue(settings.audio_merge_processing_task)
        await asyncio.to_thread(queue.enqueue,
            {"data": {"merge_id": str(job.id), "attempt_id": str(job.attempt_id)}},
            admin_functions.TaskOptions(dispatch_deadline_seconds=settings.audio_merge_timeout_seconds + 120,
                task_id=f"audiomerge-{job.id.hex}-{job.attempt_id.hex}"))
    except Exception as exc:
        # Preserve a worker claim if dispatch succeeded but acknowledgement was lost.
        attempt = job.attempt_id
        await db.refresh(job)
        locked = (await db.execute(select(AudioMerge).where(AudioMerge.id == job.id).with_for_update())).scalar_one()
        if locked.attempt_id == attempt and locked.status == "queued":
            locked.status, locked.error_code = "failed", "QUEUE_UNAVAILABLE"
            await db.commit()
            credits = CreditService(db)
            hold = await credits.reservation_id(audio_merge_reservation_key(job.id, attempt))
            if hold is not None:
                await credits.finish_failed(hold, reason="QUEUE_UNAVAILABLE")
        raise HTTPException(503, "Song Merger queue is unavailable. Please retry.") from exc
    return AudioMergeResponse.from_job(job)


@router.get("")
@limiter.limit("50/minute")
async def list_merges(request: Request, response: Response, db=Depends(get_db), user_id=Depends(rate_limit_user)):
    jobs = await AudioMergeService(db).list(credit_owner_for(request, user_id))
    return {"items": [AudioMergeResponse.from_job(job) for job in jobs]}


@router.get("/{merge_id}", response_model=AudioMergeResponse)
@limiter.limit("120/minute")
async def get_merge(merge_id: uuid.UUID, request: Request, response: Response,
                    db=Depends(get_db), user_id=Depends(rate_limit_user)):
    return AudioMergeResponse.from_job(await AudioMergeService(db).get(merge_id, credit_owner_for(request, user_id)))


@router.get("/{merge_id}/download")
@limiter.limit("20/minute")
async def download_merge(merge_id: uuid.UUID, request: Request, response: Response,
                         download: bool = Query(True), db=Depends(get_db), user_id=Depends(rate_limit_user)):
    return await AudioMergeService(db).download(merge_id, credit_owner_for(request, user_id), download)
