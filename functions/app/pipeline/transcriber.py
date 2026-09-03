"""
app/pipeline/transcriber.py

Thin pipeline-facing wrapper around integration/groq_client.transcribe_audio.
Kept as its own module (rather than calling groq_client directly from
pipeline.py) so the pipeline orchestrator depends on pipeline-stage
interfaces, not integration clients directly — mirrors the injected
embed_fn/answer_fn pattern already used in qa_log_service.
"""

from __future__ import annotations

from pathlib import Path

from app.core.logging import logger
from app.integration.groq_client import transcribe_audio


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