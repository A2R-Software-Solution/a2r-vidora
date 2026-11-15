import asyncio
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.integration import audio_merge_storage
from app.middleware.logging import logger
from app.models.audio_merge_model import AudioSource
from app.pipeline.youtube_downloader import UnsupportedVideoError, VideoTooLongError, YouTubeBotChallengeError

ACTIVE_STATUSES = {"queued", "processing"}


def stall_window() -> timedelta:
    # A source still active after this long has lost its worker.
    return timedelta(seconds=settings.audio_merge_source_timeout_seconds + 300)


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, YouTubeBotChallengeError):
        return "YOUTUBE_BLOCKED"
    if isinstance(exc, VideoTooLongError):
        return "TOO_LONG"
    if isinstance(exc, UnsupportedVideoError):
        return "UNSUPPORTED_MEDIA"
    return "SOURCE_FAILED"


async def _locked(db, source_id):
    return (await db.execute(
        select(AudioSource).where(AudioSource.id == source_id).with_for_update())).scalar_one_or_none()


async def process_audio_source(source_id):
    # Imported here so the API process does not load yt-dlp until a source is prepared inline.
    from app.pipeline.audio_source import prepare_source
    source_id = uuid.UUID(str(source_id))
    async with AsyncSessionLocal() as db:
        source = await _locked(db, source_id)
        if not source or source.status != "queued" or source.expires_at <= datetime.now(timezone.utc):
            return
        source.status, source.updated_at = "processing", datetime.now(timezone.utc)
        url = source.url
        await db.commit()

    preview_name = f"audiomerge/sources/{source_id}/preview.mp3"
    original_name = None
    try:
        with tempfile.TemporaryDirectory(prefix="vidora_source_") as directory:
            prepared = await asyncio.to_thread(prepare_source, url, directory)
            original_name = f"audiomerge/sources/{source_id}/original{prepared.original.suffix.lower()}"
            await audio_merge_storage.upload_file(preview_name, prepared.preview, "audio/mpeg")
            await audio_merge_storage.upload_file(original_name, prepared.original, "application/octet-stream")
        async with AsyncSessionLocal() as db:
            source = await _locked(db, source_id)
            if not source or source.status != "processing":
                raise RuntimeError("Source was removed while it was being prepared.")
            source.status, source.updated_at = "ready", datetime.now(timezone.utc)
            source.title = (prepared.title or "")[:300] or None
            source.duration_seconds, source.peaks = prepared.duration, prepared.peaks
            source.preview_object, source.original_object = preview_name, original_name
            await db.commit()
    except Exception as exc:
        logger.exception("audio_source_failed source_id=%s", source_id)
        for name in (preview_name, original_name):
            try:
                if name:
                    await audio_merge_storage.delete(name)
            except Exception:
                logger.exception("audio_source_cleanup_failed source_id=%s", source_id)
        async with AsyncSessionLocal() as db:
            source = await _locked(db, source_id)
            if source and source.status == "processing":
                source.status, source.error_code = "failed", _failure_code(exc)
                source.updated_at = datetime.now(timezone.utc)
                await db.commit()
