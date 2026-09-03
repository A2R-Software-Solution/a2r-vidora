from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transcript_chunk_model import TranscriptChunk
from app.repository.transcript_chunk_repository import TranscriptChunkRepository

_EMBEDDING_DIM = 384


def _top_k_for_duration(duration_seconds: int | None) -> int:
    if duration_seconds is None:
        return 5
    if duration_seconds <= 600:
        return 5
    if duration_seconds <= 1800:
        return 8
    return 12


class ChunkDimensionMismatchError(Exception):
    """Raised when an embedding does not have the expected dimensionality."""


class TranscriptChunkService:
    """Business logic layer for transcript chunk persistence and retrieval."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = TranscriptChunkRepository(db)

    async def replace_all_for_video(
        self,
        video_id: uuid.UUID,
        chunks: list[dict],
    ) -> list[TranscriptChunk]:
        """
        Re-processing rule from the test plan: old chunks must be
        deleted before new ones are inserted, not appended. Both steps
        run in the same transaction so a mid-batch failure leaves the
        previous chunk set intact rather than a partial new one.

        Each dict in `chunks` is expected to already carry validated,
        server-generated values: chunk_text, start_time, end_time,
        embedding (list[float], length 384).
        """
        for chunk in chunks:
            embedding = chunk["embedding"]
            if len(embedding) != _EMBEDDING_DIM:
                raise ChunkDimensionMismatchError(
                    f"Expected {_EMBEDDING_DIM}-dim embedding, got {len(embedding)}."
                )

        await self._repo.delete_by_video(video_id)

        new_chunks = [
            TranscriptChunk(
                video_id=video_id,
                chunk_text=chunk["chunk_text"],
                start_time=chunk["start_time"],
                end_time=chunk["end_time"],
                embedding=chunk["embedding"],
            )
            for chunk in chunks
        ]

        created = await self._repo.bulk_create(new_chunks)
        await self._db.commit()
        return created

    async def list_for_video(self, video_id: uuid.UUID) -> list[TranscriptChunk]:
        return await self._repo.list_by_video(video_id)

    async def find_relevant(
        self,
        video_id: uuid.UUID,
        query_embedding: list[float],
        query_text: str,
        *,
        video_duration_seconds: int | None = None,
    ) -> list[TranscriptChunk]:
        """
        Retrieval step for the Ask Video flow. Always scoped to a single
        video_id — this is the boundary that prevents one user's question
        from ever surfacing another video's transcript content.

        top_k scales with video length: longer videos have more chunks
        and benefit from a wider retrieval window.
        """
        if len(query_embedding) != _EMBEDDING_DIM:
            raise ChunkDimensionMismatchError(
                f"Expected {_EMBEDDING_DIM}-dim query embedding, got {len(query_embedding)}."
            )
        top_k = _top_k_for_duration(video_duration_seconds)
        return await self._repo.hybrid_search(
            video_id, query_embedding, query_text, top_k=top_k
        )

    async def find_in_time_range(
        self,
        video_id: uuid.UUID,
        start_seconds: float,
        end_seconds: float,
    ) -> list[TranscriptChunk]:
        """
        Retrieval step for time-anchored questions ("what was said
        between 0:45 and 1:47?") — bypasses semantic/keyword search
        entirely in favor of a direct timestamp-range lookup, since a
        literal time string rarely matches chunk_text well semantically.
        """
        return await self._repo.find_in_time_range(video_id, start_seconds, end_seconds)