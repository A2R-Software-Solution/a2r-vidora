"""
app/pipeline/pipeline.py

Orchestrates the full video-ingestion flow for a single video:

    download -> mark_metadata -> transcribe -> chunk -> embed
             -> replace_all_for_video -> summarize -> mark_completed

On any failure, the video is moved to FAILED rather than left stuck
in PROCESSING, and the exception is re-raised so the caller (route /
background task runner) can log/alert on it.

This module is synchronous-call-order but async in execution — it does
NOT itself handle "run this in the background off the request"; that
concern belongs to the caller (see checkpoint item #6, not yet done).
For now this is invoked directly and will block the request until
async/background execution is wired in.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.video_model import Video
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

    video = await video_service.get_for_user(video_id, user_id=None)

    try:
        with make_temp_dir() as tmp_dir:
            download_result = await download_audio(youtube_url, output_dir=tmp_dir)

            video = await video_service.mark_metadata(
                video,
                title=download_result.title,
                duration=download_result.duration,
            )

            segments = await transcriber.transcribe(download_result.audio_path)

        chunks = chunker.chunk_segments(segments)
        embedded_chunks = await embedder.embed_chunks(chunks)

        await chunk_service.replace_all_for_video(video.id, embedded_chunks)

        summary = await summarizer.summarize(embedded_chunks)

        video = await video_service.mark_completed(video, summary=summary)
        logger.info(f"Pipeline completed for video {video.id}")
        return video

    except Exception as exc:
        logger.error(f"Pipeline failed for video {video.id} ({type(exc).__name__})")
        await video_service.mark_failed(video)
        raise PipelineError(f"Ingestion pipeline failed for video {video.id}") from exc