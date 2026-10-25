import asyncio
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.audio_merge_model import AudioMerge
from app.pipeline.audio_merger import MergeError, merge_audio
from app.integration import audio_merge_storage
from app.middleware.logging import logger
from app.services.credit_service import CreditService, audio_merge_reservation_key


async def _finish_credits(merge_id, attempt_id, *, succeeded: bool, reason: str | None = None) -> None:
    """Settles or refunds this attempt's hold. A failure here is only logged:
    the cleanup job reconciles any hold left open."""
    try:
        async with AsyncSessionLocal() as db:
            credits = CreditService(db)
            hold = await credits.reservation_id(audio_merge_reservation_key(merge_id, attempt_id))
            if hold is None:
                return
            if succeeded:
                await credits.settle(hold)
            else:
                await credits.finish_failed(hold, reason=reason)
    except Exception:
        logger.exception("audio_merge_credit_finish_failed merge_id=%s", merge_id)


async def _fail(merge_id, attempt_id, code):
    async with AsyncSessionLocal() as db:
        job = (await db.execute(select(AudioMerge).where(AudioMerge.id == merge_id).with_for_update())).scalar_one_or_none()
        if job and job.attempt_id == attempt_id and job.status == "processing":
            job.status, job.error_code = "failed", code
            job.updated_at = datetime.now(timezone.utc)
            await db.commit()
    await _finish_credits(merge_id, attempt_id, succeeded=False, reason=code)


async def process_audio_merge(merge_id, attempt_id):
    merge_id, attempt_id = uuid.UUID(merge_id), uuid.UUID(attempt_id)
    async with AsyncSessionLocal() as db:
        job = (await db.execute(select(AudioMerge).where(AudioMerge.id == merge_id).with_for_update())).scalar_one_or_none()
        if not job or job.attempt_id != attempt_id or job.status != "queued":
            return
        if job.expires_at <= datetime.now(timezone.utc):
            job.status = "expired"
            await db.commit()
            await _finish_credits(merge_id, attempt_id, succeeded=False, reason="expired")
            return
        job.status, job.updated_at = "processing", datetime.now(timezone.utc)
        tracks, output_format, crossfade = job.tracks, job.output_format, job.crossfade_seconds
        await db.commit()
    object_name = f"audiomerge/{merge_id}/{attempt_id}.{output_format}"
    inputs = [t["object_name"] for t in tracks if t.get("object_name")]
    try:
        with tempfile.TemporaryDirectory(prefix="vidora_merge_") as directory:
            uploads = {}
            for index, track in enumerate(tracks):
                if track["source"] == "upload":
                    path = Path(directory) / f"up{index}{Path(track['object_name']).suffix}"
                    await audio_merge_storage.download(track["object_name"], path)
                    uploads[index] = path
            path = await asyncio.to_thread(merge_audio, tracks, uploads, output_format, crossfade, directory)
            await audio_merge_storage.upload(object_name, path, output_format)
        async with AsyncSessionLocal() as db:
            job = (await db.execute(select(AudioMerge).where(AudioMerge.id == merge_id).with_for_update())).scalar_one_or_none()
            if not job or job.attempt_id != attempt_id or job.status != "processing" or job.expires_at <= datetime.now(timezone.utc):
                await audio_merge_storage.delete(object_name)
                return
            job.status, job.object_name, job.updated_at = "completed", object_name, datetime.now(timezone.utc)
            await db.commit()
        await _finish_credits(merge_id, attempt_id, succeeded=True)
    except Exception as exc:
        logger.exception("audio_merge_failed merge_id=%s", merge_id)
        try:
            await audio_merge_storage.delete(object_name)
        except Exception:
            logger.exception("audio_merge_upload_cleanup_failed merge_id=%s", merge_id)
        await _fail(merge_id, attempt_id, exc.code if isinstance(exc, MergeError) else "MERGE_FAILED")
    finally:
        # The uploaded sources are only needed while merging.
        for name in inputs:
            try:
                await audio_merge_storage.delete(name)
            except Exception:
                logger.exception("audio_merge_input_cleanup_failed merge_id=%s", merge_id)
