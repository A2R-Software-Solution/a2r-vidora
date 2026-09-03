from __future__ import annotations

import math
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_EMBEDDING_DIM: int = 384
_MAX_CHUNK_TEXT_LEN: int = 8000  # service-layer sanity cap, not a hard product limit


class _ChunkBase(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        str_min_length=1,
        frozen=False,
    )



class TranscriptChunkCreate(_ChunkBase):
    """
    Internal payload used by the ingestion pipeline to persist a chunk.
    video_id is set server-side from the current processing job — never
    accepted from a client request.
    """

    video_id: uuid.UUID | None = Field(
        default=None,
        description="Parent video id, set server-side by the pipeline.",
    )
    chunk_text: str = Field(
        ...,
        max_length=_MAX_CHUNK_TEXT_LEN,
        description="Transcript segment text from STT output.",
    )
    start_time: float = Field(..., description="Chunk start offset in seconds.")
    end_time: float = Field(..., description="Chunk end offset in seconds.")
    embedding: list[float] = Field(
        ...,
        description="MiniLM embedding vector, must be exactly 384 dimensions.",
    )


    @field_validator("chunk_text")
    @classmethod
    def validate_chunk_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("chunk_text must not be empty or whitespace-only.")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_finite_time(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("time value must be a finite number (no NaN/Infinity).")
        if v < 0:
            raise ValueError("time value must not be negative.")
        return v

    @field_validator("embedding")
    @classmethod
    def validate_embedding(cls, v: list[float]) -> list[float]:
        if len(v) != _EMBEDDING_DIM:
            raise ValueError(
                f"embedding must be exactly {_EMBEDDING_DIM} dimensions, got {len(v)}."
            )
        for value in v:
            if value is None:
                raise ValueError("embedding must not contain null elements.")
            if math.isnan(value) or math.isinf(value):
                raise ValueError("embedding must not contain NaN/Infinity values.")
        return v

    # -- Cross-field validator ------------------------------------------------

    @model_validator(mode="after")
    def validate_time_range(self) -> "TranscriptChunkCreate":
        if self.end_time <= self.start_time:
            raise ValueError(
                "end_time must be strictly greater than start_time "
                "(zero-length or inverted ranges are invalid)."
            )
        return self

class TranscriptChunkResponse(_ChunkBase):
    """
    Full read-only schema mapping directly to the DB row.
    Not returned to clients as-is — use TranscriptChunkPublic for that.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Primary key (UUID v4).")
    video_id: uuid.UUID | None = Field(..., description="Parent video id.")
    chunk_text: str = Field(..., description="Transcript segment text.")
    start_time: float = Field(..., description="Chunk start offset in seconds.")
    end_time: float = Field(..., description="Chunk end offset in seconds.")
    created_at: datetime = Field(..., description="UTC timestamp of chunk creation.")

    # embedding intentionally omitted — internal retrieval artifact only,
    # never serialised in any response (see security section of test plan)


# ---------------------------------------------------------------------------
# Schema: TranscriptChunkInDB  (internal use only — never returned to client)
# ---------------------------------------------------------------------------

class TranscriptChunkInDB(TranscriptChunkResponse):
    """
    Internal schema for service-layer use only — the only schema variant
    permitted to carry the raw embedding, for similarity-search plumbing.
    """

    embedding: list[float] = Field(..., description="Raw MiniLM embedding vector.")


class TranscriptChunkPublic(_ChunkBase):
    """
    Minimal public projection of a chunk — safe to embed inside an
    Ask Video response. No id, video_id, embedding, or created_at.
    """

    model_config = ConfigDict(from_attributes=True)

    chunk_text: str
    start_time: float
    end_time: float