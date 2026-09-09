"""
app/pipeline/embedder.py

Attaches a MiniLM embedding to each chunk produced by chunker.py.
Kept separate from chunker so chunking logic has no model dependency,
and separate from integration/embedding_client so pipeline.py depends
on a pipeline-stage interface rather than the client directly.
"""

from __future__ import annotations

from app.core.logging import logger
from app.integration.embedding_client import embed_texts


async def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Takes chunks shaped {"chunk_text", "start_time", "end_time"} and
    returns the same dicts with an "embedding" key (list[float], 384-dim)
    added, ready for transcript_chunk_service.replace_all_for_video().

    Encodes chunks in batches with one cached model and bounded batch memory.
    """
    if not chunks:
        return []

    logger.info(f"Embedding {len(chunks)} chunks")
    vectors = await embed_texts([chunk["chunk_text"] for chunk in chunks])
    embedded = [{**chunk, "embedding": vector} for chunk, vector in zip(chunks, vectors, strict=True)]
    logger.info(f"Embedded {len(embedded)} chunks")
    return embedded
