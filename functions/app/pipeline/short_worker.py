import asyncio
import tempfile
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.short_model import Short
from app.models.video_model import Video
from app.repository.transcript_chunk_repository import TranscriptChunkRepository
from app.pipeline.short_renderer import render_short
from app.integration import short_storage
from app.middleware.logging import logger


async def process_short(short_id, attempt_id):
    short_id, attempt_id = uuid.UUID(short_id), uuid.UUID(attempt_id)
    async with AsyncSessionLocal() as db:
        job = (await db.execute(select(Short).where(Short.id == short_id).with_for_update())).scalar_one_or_none()
        if not job or job.attempt_id != attempt_id or job.status != "queued":
            return
        if job.expires_at <= datetime.now(timezone.utc):
            job.status = "expired"
            await db.commit()
            return
        job.status, job.updated_at = "rendering", datetime.now(timezone.utc)
        video = await db.get(Video, job.video_id)
        chunks = await TranscriptChunkRepository(db).find_in_time_range(job.video_id, job.start_time, job.end_time)
        url, start, end = video.youtube_url, job.start_time, job.end_time
        await db.commit()
    object_name = f"shorts/{short_id}/{attempt_id}.mp4"
    try:
        with tempfile.TemporaryDirectory(prefix="vidora_short_") as directory:
            path = await asyncio.to_thread(render_short, url, start, end, chunks, directory)
            await short_storage.upload(object_name, path)
        async with AsyncSessionLocal() as db:
            job = (await db.execute(select(Short).where(Short.id == short_id).with_for_update())).scalar_one_or_none()
            if not job or job.attempt_id != attempt_id or job.status != "rendering" or job.expires_at <= datetime.now(timezone.utc):
                await short_storage.delete(object_name)
                return
            job.status, job.object_name, job.updated_at = "completed", object_name, datetime.now(timezone.utc)
            await db.commit()
    except Exception:
        logger.exception("short_render_failed short_id=%s", short_id)
        # Delete partial uploads; failed attempts don't consume the allowance.
        try:
            await short_storage.delete(object_name)
        except Exception:
            logger.exception("short_upload_cleanup_failed short_id=%s", short_id)
        async with AsyncSessionLocal() as db:
            job = (await db.execute(select(Short).where(Short.id == short_id).with_for_update())).scalar_one_or_none()
            if job and job.attempt_id == attempt_id and job.status == "rendering":
                job.status, job.error_code = "failed", "RENDER_FAILED"
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
