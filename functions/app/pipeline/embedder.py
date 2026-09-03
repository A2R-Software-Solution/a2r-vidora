"""
app/pipeline/embedder.py

Attaches a MiniLM embedding to each chunk produced by chunker.py.
Kept separate from chunker so chunking logic has no model dependency,
and separate from integration/embedding_client so pipeline.py depends
on a pipeline-stage interface rather than the client directly.
"""

from __future__ import annotations

import asyncio

from app.core.logging import logger
from app.integration.embedding_client import embed_text

# Caps concurrent in-flight embedding calls so a long video doesn't
# spawn hundreds of simultaneous CPU-bound thread-executor tasks.
_MAX_CONCURRENT_EMBEDDINGS = 8


async def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Takes chunks shaped {"chunk_text", "start_time", "end_time"} and
    returns the same dicts with an "embedding" key (list[float], 384-dim)
    added, ready for transcript_chunk_service.replace_all_for_video().

    Runs embeddings concurrently (bounded by a semaphore) rather than
    sequentially, since embed_text is I/O-executor-bound per call.
    """
    if not chunks:
        return []

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_EMBEDDINGS)

    async def embed_one(chunk: dict) -> dict:
        async with semaphore:
            vector = await embed_text(chunk["chunk_text"])
        return {**chunk, "embedding": vector}

    logger.info(f"Embedding {len(chunks)} chunks")
    embedded = await asyncio.gather(*(embed_one(chunk) for chunk in chunks))
    logger.info(f"Embedded {len(embedded)} chunks")
    return embedded