from __future__ import annotations

import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transcript_chunk_model import TranscriptChunk

_RRF_K = 60  # standard RRF smoothing constant


class TranscriptChunkRepository:
    """Encapsulates all SQL access for the `transcript_chunks` table."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, chunk_id: uuid.UUID) -> TranscriptChunk | None:
        result = await self._db.execute(
            select(TranscriptChunk).where(TranscriptChunk.id == chunk_id)
        )
        return result.scalar_one_or_none()

    async def list_by_video(self, video_id: uuid.UUID) -> list[TranscriptChunk]:
        result = await self._db.execute(
            select(TranscriptChunk)
            .where(TranscriptChunk.video_id == video_id)
            .order_by(TranscriptChunk.start_time.asc())
        )
        return list(result.scalars().all())

    async def bulk_create(
        self, chunks: list[TranscriptChunk]
    ) -> list[TranscriptChunk]:
        self._db.add_all(chunks)
        await self._db.flush()
        for chunk in chunks:
            await self._db.refresh(chunk)
        return chunks

    async def delete_by_video(self, video_id: uuid.UUID) -> None:
        """
        Deletes all chunks for a video in one statement — used when a
        video is being re-processed (old chunks must be replaced, not
        appended) or when a video's data is being purged on expiry.
        """
        await self._db.execute(
            sa_delete(TranscriptChunk).where(TranscriptChunk.video_id == video_id)
        )
        await self._db.flush()

    async def search_similar(
        self,
        video_id: uuid.UUID,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[TranscriptChunk]:
        """
        Cosine-similarity search scoped to a single video_id — never
        searches across videos (see security section of the test plan).
        Requires pgvector's cosine_distance operator on the embedding
        column; lower distance == more similar.
        """
        result = await self._db.execute(
            select(TranscriptChunk)
            .where(TranscriptChunk.video_id == video_id)
            .order_by(TranscriptChunk.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_in_time_range(
        self,
        video_id: uuid.UUID,
        start_seconds: float,
        end_seconds: float,
    ) -> list[TranscriptChunk]:
        """
        Fetches chunks whose [start_time, end_time] window overlaps the
        requested [start_seconds, end_seconds] range, ordered
        chronologically. Uses overlap rather than exact containment so
        a chunk that starts just before start_seconds (but still
        covers part of the requested range) isn't missed — matches how
        a person would expect "what was said between X and Y" to work.
        """
        result = await self._db.execute(
            select(TranscriptChunk)
            .where(TranscriptChunk.video_id == video_id)
            .where(TranscriptChunk.start_time <= end_seconds)
            .where(TranscriptChunk.end_time >= start_seconds)
            .order_by(TranscriptChunk.start_time.asc())
        )
        return list(result.scalars().all())

    async def hybrid_search(
        self,
        video_id: uuid.UUID,
        query_embedding: list[float],
        query_text: str,
        *,
        top_k: int = 5,
    ) -> list[TranscriptChunk]:
        """
        Combines pgvector semantic search and Postgres full-text search
        via Reciprocal Rank Fusion — no manual weight tuning between
        the two signals. Scoped to a single video_id, same as
        search_similar().
        """
        candidate_pool = max(top_k * 4, 20)

        sql = text(
            """
            with semantic as (
                select id, row_number() over (
                    order by embedding <=> :query_embedding
                ) as rank
                from transcript_chunks
                where video_id = :video_id
                order by embedding <=> :query_embedding
                limit :candidate_pool
            ),
            keyword as (
                select id, row_number() over (
                    order by ts_rank(search_vector, plainto_tsquery('english', :query_text)) desc
                ) as rank
                from transcript_chunks
                where video_id = :video_id
                  and search_vector @@ plainto_tsquery('english', :query_text)
                limit :candidate_pool
            ),
            fused as (
                select
                    coalesce(semantic.id, keyword.id) as id,
                    (1.0 / (:rrf_k + coalesce(semantic.rank, :candidate_pool + 1)))
                    + (1.0 / (:rrf_k + coalesce(keyword.rank, :candidate_pool + 1))) as score
                from semantic
                full outer join keyword on semantic.id = keyword.id
            )
            select id from fused order by score desc limit :top_k
            """
        )

        result = await self._db.execute(
            sql,
            {
                "video_id": video_id,
                "query_embedding": str(query_embedding),
                "query_text": query_text,
                "candidate_pool": candidate_pool,
                "rrf_k": _RRF_K,
                "top_k": top_k,
            },
        )
        ordered_ids = [row[0] for row in result.all()]
        if not ordered_ids:
            return []

        chunks_result = await self._db.execute(
            select(TranscriptChunk).where(TranscriptChunk.id.in_(ordered_ids))
        )
        chunks_by_id = {chunk.id: chunk for chunk in chunks_result.scalars().all()}
        return [chunks_by_id[cid] for cid in ordered_ids if cid in chunks_by_id]