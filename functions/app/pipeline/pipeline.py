"""
app/pipeline/pipeline.py

Orchestrates the full video-ingestion flow for a single video:

    download -> mark_metadata -> VAD/merge -> bounded parallel chunk STT
             -> timestamp/overlap assembly -> text chunk -> embed -> summarize
             -> atomically replace_all_for_video + mark_completed

On any failure, the video is moved to FAILED rather than left stuck
in PROCESSING, and the exception is re-raised so the caller (route /
background task runner) can log/alert on it.

Cloud Tasks invokes this worker after the API has persisted and queued a job.
"""

from __future__ import annotations

import uuid
import asyncio
from time import monotonic
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.logging import logger, log_exception_group
from app.core.config import settings
from app.models.video_model import Video, VideoStatus
from app.pipeline import audio_chunker, chunker, embedder, summarizer, transcriber
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

    async def record_stage(next_stage: str, *, total_chunks: int | None = None,
                           completed_chunks: int | None = None) -> None:
        nonlocal stage
        stage = next_stage
        if video is not None:
            await video_service.mark_progress(video, stage=stage, total_chunks=total_chunks,
                                              completed_chunks=completed_chunks)
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
            await record_stage("download")
            duration_limit = (settings.max_video_duration_seconds if video.user_id is not None
                              else settings.anonymous_max_video_duration_seconds)
            download_result = await download_audio(youtube_url, output_dir=tmp_dir,
                                                   max_duration_seconds=duration_limit)

            video = await video_service.mark_metadata(
                video,
                title=download_result.title,
                duration=download_result.duration,
            )

            await record_stage("vad_chunking")
            batch = await audio_chunker.prepare_audio_async(
                download_result.audio_path, output_root=Path(tmp_dir),
                settings=settings.vad, source_id=video_id,
            )
            logger.info("audio_chunks_ready video_id=%s count=%s", video_id, len(batch.chunks))
            await record_stage("chunk_transcription", total_chunks=len(batch.chunks))
            segments = await transcriber.transcribe_chunks(batch)
            await record_stage("chunk_transcription", total_chunks=len(batch.chunks), completed_chunks=len(batch.chunks))

        chunks = chunker.chunk_segments(segments)
        await record_stage("embed")
        embedded_chunks = await embedder.embed_chunks(chunks)

        await record_stage("summarize")
        summary = await summarizer.summarize(embedded_chunks)

        await record_stage("persist")
        await chunk_service.replace_all_for_video(video.id, embedded_chunks, commit=False)
        video = await video_service.mark_completed(video, summary=summary)
        await record_stage("completed", completed_chunks=video.processing_total_chunks)
        logger.info(f"Pipeline completed for video {video.id}")
        return video

    except (Exception, asyncio.CancelledError) as exc:
        log_exception_group(
            event="analysis_failure_detail",
            exc=exc,
            video_id=video_id,
            stage=stage,
        )
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
