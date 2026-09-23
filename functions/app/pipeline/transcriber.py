"""
app/pipeline/transcriber.py

Bounded-parallel VAD-chunk STT and timestamp assembly for ingestion. The legacy
single-file wrapper remains available; the product pipeline uses transcribe_chunks.
"""

from __future__ import annotations

import asyncio
import random
import hashlib
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.middleware.logging import logger
from app.core.config import settings
from app.integration.groq_client import (transcribe_audio, transcribe_audio_words,
                                         EmptyTranscriptionError, GroqTransientError)
from app.integration.stt_quota import reserve_stt_request
from app.integration.stt_quota import SttQuotaDeferred
from app.db.session import AsyncSessionLocal
from app.repository.stt_checkpoint_repository import SttCheckpointRepository
from app.pipeline.audio_chunker import AudioBatch, SAMPLE_RATE
from app.pipeline.stt_packer import map_request_words, pack_stt_requests


async def transcribe_chunks(batch: AudioBatch, *,
                            progress: Callable[[int, int], Awaitable[None]] | None = None,
                            video_id: uuid.UUID | None = None) -> list[dict]:
    """Pack VAD clips, enforce shared quotas, and assemble by video time."""
    if not batch.chunks:
        raise EmptyTranscriptionError("No speech detected in this video.")
    if len(batch.paths) != len(batch.chunks):
        raise ValueError("Audio manifest/file count mismatch")
    requests = pack_stt_requests(batch, settings.vad)
    if progress:
        await progress(0, len(requests))
    results: dict[int, list[dict]] = {}
    semaphore = asyncio.Semaphore(settings.stt_concurrency)
    progress_lock = asyncio.Lock()

    async def transcribe_one(request) -> tuple[int, list[dict]]:
        async with semaphore:
            digest = hashlib.sha256(request.path.read_bytes()).hexdigest() if video_id else ""
            if video_id:
                async with AsyncSessionLocal() as session:
                    cached = await SttCheckpointRepository(session).get(video_id, request.first_sequence, digest)
                if cached is not None:
                    return request.first_sequence, cached
            for attempt in range(4):
                await reserve_stt_request(request.audio_seconds)
                try:
                    words = await transcribe_audio_words(str(request.path))
                    segments = map_request_words(request, words)
                    if video_id:
                        async with AsyncSessionLocal() as session:
                            async with session.begin():
                                await SttCheckpointRepository(session).save(
                                    video_id, request.first_sequence, digest, segments)
                    logger.info("stt_request_completed first=%s last=%s", request.first_sequence, request.last_sequence)
                    return request.first_sequence, segments
                except GroqTransientError as exc:
                    if attempt == 3:
                        raise
                    if exc.retry_after > 10:
                        raise SttQuotaDeferred(exc.retry_after + 2) from exc
                    await asyncio.sleep(max(exc.retry_after, min(2 ** attempt, 8)) + random.uniform(0, 0.5))
            raise AssertionError("unreachable")

    tasks = [asyncio.create_task(transcribe_one(request)) for request in requests]
    failures = []
    try:
        for completed in asyncio.as_completed(tasks):
            try:
                first_sequence, segments = await completed
                results[first_sequence] = segments
                if progress:
                    async with progress_lock:
                        await progress(len(results), len(requests))
            except Exception as exc:
                failures.append(exc)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if failures:
        raise next((exc for exc in failures if not isinstance(exc, SttQuotaDeferred)), failures[0])
    segments = []
    for index, request in enumerate(requests):
        left = request.start_sample / SAMPLE_RATE
        right = request.end_sample / SAMPLE_RATE
        if index:
            previous = requests[index - 1]
            left = (previous.end_sample + request.start_sample) / (2 * SAMPLE_RATE)
        if index + 1 < len(requests):
            following = requests[index + 1]
            right = (request.end_sample + following.start_sample) / (2 * SAMPLE_RATE)
        segments.extend(segment for segment in results[request.first_sequence]
                        if left <= (segment["start"] + segment["end"]) / 2 < right)
    segments.sort(key=lambda segment: (segment["start"], segment["end"]))
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
