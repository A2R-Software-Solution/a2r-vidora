"""
app/pipeline/chunker.py

Groups Whisper's natural segment boundaries into transcript chunks
sized for retrieval — NOT fixed 30-second windows. Whisper already
splits on speech pauses/sentence boundaries; we merge small adjacent
segments up to a target character budget so chunks are neither too
granular (poor semantic content per chunk) nor too coarse (poor
retrieval precision).
"""

from __future__ import annotations

from app.core.logging import logger

# Target chunk size in characters — MiniLM handles short passages well;
# this keeps each chunk close to one coherent thought without being
# so small that retrieval loses context.
_TARGET_CHUNK_CHARS = 500
_MAX_CHUNK_CHARS = 800


class EmptySegmentsError(Exception):
    """Raised when there are no Whisper segments to chunk."""


def chunk_segments(segments: list[dict]) -> list[dict]:
    """
    Merges Whisper segments into chunks of roughly _TARGET_CHUNK_CHARS,
    never exceeding _MAX_CHUNK_CHARS, without splitting a segment.

    Input: [{"text": str, "start": float, "end": float}, ...] in order.
    Output: [{"chunk_text": str, "start_time": float, "end_time": float}, ...]
    (embedding key is added later by embedder.py — kept separate so
    this stage has no dependency on the embedding model.)
    """
    if not segments:
        raise EmptySegmentsError("No segments provided to chunk.")

    chunks: list[dict] = []
    current_texts: list[str] = []
    current_start: float | None = None
    current_end: float | None = None
    current_len = 0

    def flush() -> None:
        if current_texts:
            chunks.append(
                {
                    "chunk_text": " ".join(current_texts).strip(),
                    "start_time": current_start,
                    "end_time": current_end,
                }
            )

    for segment in segments:
        text = segment["text"].strip()
        if not text:
            continue

        projected_len = current_len + len(text) + 1  # +1 for the joining space

        if current_texts and projected_len > _MAX_CHUNK_CHARS:
            flush()
            current_texts = []
            current_len = 0
            current_start = None

        if current_start is None:
            current_start = segment["start"]

        current_texts.append(text)
        current_end = segment["end"]
        current_len += len(text) + 1

        if current_len >= _TARGET_CHUNK_CHARS:
            flush()
            current_texts = []
            current_len = 0
            current_start = None

    flush()

    logger.info(f"Chunked {len(segments)} segments into {len(chunks)} chunks")
    return chunks