"""
app/pipeline/pipeline.py

Orchestrates the full video-ingestion flow for a single video:

    download -> mark_metadata -> transcribe -> chunk -> embed
             -> replace_all_for_video -> summarize -> mark_completed

On any failure, the video is moved to FAILED rather than left stuck
in PROCESSING, and the exception is re-raised so the caller (route /
background task runner) can log/alert on it.

New submissions await this pipeline inside the HTTP invocation. A legacy
task worker remains compatible with previously queued jobs.
"""

from __future__ import annotations

import uuid
import asyncio
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.video_model import Video, VideoStatus
from app.pipeline import chunker, embedder, summarizer, transcriber
from app.pipeline.youtube_downloader import download_audio, make_temp_dir
from app.services.transcript_chunk_service import TranscriptChunkService
from app.services.video_service import VideoService


class PipelineError(Exception):
    """
    Raised when the ingestion pipeline fails at any stage.

    The video has already been marked FAILED by the time this is
    raised — callers should log/alert, not attempt to recover state.
    """


async def run_pipeline(video_id: uuid.UUID, youtube_url: str, *, db: AsyncSession) -> Video:
    """
    Runs the full ingestion pipeline for `video_id`, which must already
    exist in PROCESSING state (created via video_service.submit()).

    Uses the same `db` session throughout so all writes made by the
    services this pipeline calls happen against one connection.
    """
    video_service = VideoService(db)
    chunk_service = TranscriptChunkService(db)
    video: Video | None = None
    started = monotonic()
    stage = "lookup"

    def record_stage(next_stage: str) -> None:
        nonlocal stage
        stage = next_stage
        logger.info("analysis_stage video_id=%s stage=%s elapsed_seconds=%.2f",
                       video_id, stage, monotonic() - started)

    try:
        video = await video_service.get_for_processing(video_id)

        # Cloud Tasks may redeliver a task after a response/network failure.
        # A completed job is already durable and must not incur API costs twice.
        if video.status == VideoStatus.COMPLETED:
            logger.info(f"Skipping already-completed video {video.id}")
            return video

        with make_temp_dir() as tmp_dir:
            record_stage("download")
            download_result = await download_audio(youtube_url, output_dir=tmp_dir)

            video = await video_service.mark_metadata(
                video,
                title=download_result.title,
                duration=download_result.duration,
            )

            record_stage("transcribe")
            segments = await transcriber.transcribe(download_result.audio_path)

        chunks = chunker.chunk_segments(segments)
        record_stage("embed")
        embedded_chunks = await embedder.embed_chunks(chunks)

        await chunk_service.replace_all_for_video(video.id, embedded_chunks)

        record_stage("summarize")
        summary = await summarizer.summarize(embedded_chunks)

        video = await video_service.mark_completed(video, summary=summary)
        record_stage("completed")
        logger.info(f"Pipeline completed for video {video.id}")
        return video

    except (Exception, asyncio.CancelledError) as exc:
        logger.error("analysis_failed video_id=%s stage=%s elapsed_seconds=%.2f error_type=%s",
                     video_id, stage, monotonic() - started, type(exc).__name__)
        if video is not None:
            try:
                # A failed flush leaves the SQLAlchemy session unusable until
                # rollback. Re-fetch before recording the terminal status.
                await db.rollback()
                video = await video_service.get_for_processing(video_id)
                await video_service.mark_failed(video)
            except Exception:
                logger.exception(f"Could not mark video {video_id} as failed")
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise PipelineError(f"Ingestion pipeline failed for video {video_id}") from exc
