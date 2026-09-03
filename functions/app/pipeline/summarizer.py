"""
app/pipeline/summarizer.py

Produces a short summary of a video from its (already embedded)
transcript chunks. Kept separate from embedder.py so pipeline.py
depends on a pipeline-stage interface rather than the Groq client
directly — mirrors the embedder.py / embedding_client split.
"""

from __future__ import annotations

from app.core.logging import logger
from app.integration.groq_client import generate_summary


async def summarize(chunks: list[dict]) -> str:
    """
    Takes chunks shaped {"chunk_text", "start_time", "end_time", ...}
    (as produced by chunker.py / embedder.py) and returns a short
    prose summary of the full video, generated via Groq.

    Joins chunk_text in order to reconstruct the full transcript text;
    generate_summary() handles truncation for very long transcripts.
    """
    if not chunks:
        raise ValueError("chunks must not be empty.")

    full_transcript_text = " ".join(
        chunk["chunk_text"].strip() for chunk in chunks if chunk.get("chunk_text", "").strip()
    )

    logger.info(f"Summarizing transcript ({len(chunks)} chunks)")
    summary = await generate_summary(full_transcript_text)
    logger.info("Summary generated")
    return summary