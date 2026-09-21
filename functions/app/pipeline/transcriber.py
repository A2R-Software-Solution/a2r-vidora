"""
app/pipeline/transcriber.py

Bounded-parallel VAD-chunk STT and timestamp assembly for ingestion. The legacy
single-file wrapper remains available; the product pipeline uses transcribe_chunks.
"""

from __future__ import annotations

from pathlib import Path
import asyncio

from app.core.logging import logger
from app.core.config import settings
from app.integration.groq_client import transcribe_audio, transcribe_audio_words, EmptyTranscriptionError
from app.pipeline.audio_chunker import AudioBatch
from app.pipeline.transcript_assembler import assemble_words


async def transcribe_chunks(batch: AudioBatch) -> list[dict]:
    """Bounded parallel STT, assembled deterministically by chunk identity."""
    if not batch.chunks:
        raise EmptyTranscriptionError("No speech detected in this video.")
    if len(batch.paths) != len(batch.chunks):
        raise ValueError("Audio manifest/file count mismatch")
    results: dict[str, list[dict]] = {}
    semaphore = asyncio.Semaphore(settings.stt_concurrency)

    async def transcribe_one(chunk, path: Path) -> tuple[str, list[dict]]:
        async with semaphore:
            # Results are keyed by stable VAD ID, never completion order.
            # TaskGroup cancels queued siblings if one chunk fails, preventing
            # unnecessary paid requests; in-flight provider requests may finish.
            logger.info("chunk_stt_started chunk_id=%s sequence=%s total=%s", chunk.id, chunk.sequence_number, len(batch.chunks))
            words = await transcribe_audio_words(str(path))
            logger.info("chunk_stt_completed chunk_id=%s sequence=%s", chunk.id, chunk.sequence_number)
            return chunk.id, words

    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(transcribe_one(chunk, path))
            for chunk, path in zip(batch.chunks, batch.paths)
        ]
    for task in tasks:
        chunk_id, words = task.result()
        results[chunk_id] = words
    segments = assemble_words(batch.chunks, results)
    if not segments:
        raise EmptyTranscriptionError("No usable speech returned for this video.")
    return segments


async def transcribe(audio_path: Path) -> list[dict]:
    """
    Transcribes the audio file at `audio_path` and returns segment
    dicts: [{"text": str, "start": float, "end": float}, ...].

    Propagates GroqRequestError / EmptyTranscriptionError from
    groq_client as-is — pipeline.py is responsible for catching these
    and calling video_service.mark_failed().
    """
    logger.info(f"Transcribing {audio_path}")
    segments = await transcribe_audio(str(audio_path))
    logger.info(f"Transcription produced {len(segments)} segments")
    return segments
