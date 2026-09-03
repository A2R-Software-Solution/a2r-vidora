from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.video_model import VideoStatus
from app.utils.youtube import extract_youtube_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_YOUTUBE_URL_MAX_LEN: int = 500
_MAX_DURATION_SECONDS: int = 3 * 60 * 60  # 3 hour cap, per README abuse controls


# ---------------------------------------------------------------------------
# Base config shared by all Video schemas
# ---------------------------------------------------------------------------

class _VideoBase(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        str_min_length=1,
        frozen=False,
    )


# ---------------------------------------------------------------------------
# Schema: VideoCreate
# Used by: POST /videos/analyze
# The client sends only the URL — id, youtube_id, title, duration, status,
# created_at, expires_at are all set server-side by the pipeline.
# ---------------------------------------------------------------------------

class VideoCreate(_VideoBase):
    """
    Payload required to submit a video for analysis.
    Only youtube_url is client-facing — everything else (youtube_id,
    title, duration, status, timestamps) is derived or set server-side.
    """

    youtube_url: str = Field(
        ...,
        max_length=_YOUTUBE_URL_MAX_LEN,
        description="Full YouTube watch URL.",
    )

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        if any(ch.isspace() for ch in v):
            raise ValueError("youtube_url must not contain whitespace.")
        # Raises ValueError itself if invalid — validates domain, scheme,
        # path shape, and video id format before this ever reaches yt-dlp.
        extract_youtube_id(v)
        return v


# ---------------------------------------------------------------------------
# Schema: VideoResponse
# Used by: all endpoints that return a full video object
# ---------------------------------------------------------------------------

class VideoResponse(_VideoBase):
    """
    Read-only schema returned from API responses.
    Maps directly to the DB row. `summary` is null until status is
    'completed'. `status: failed` never leaks internal error detail —
    that belongs in server-side logs only, not this schema.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Primary key (UUID v4).")
    user_id: uuid.UUID | None = Field(..., description="Owning user, null if anonymous.")
    youtube_id: str = Field(..., description="11-character YouTube video id.")
    youtube_url: str = Field(..., description="Original YouTube watch URL.")
    title: str | None = Field(..., description="Video title from YouTube metadata.")
    duration: int | None = Field(..., description="Video duration in seconds.")
    status: VideoStatus = Field(..., description="Processing state.")
    summary: str | None = Field(..., description="LLM-generated summary, null until completed.")
    created_at: datetime = Field(..., description="UTC timestamp video was submitted.")
    expires_at: datetime = Field(..., description="UTC timestamp data will be deleted.")


# ---------------------------------------------------------------------------
# Schema: VideoInDB  (internal use only — never returned to client)
# ---------------------------------------------------------------------------

class VideoInDB(VideoResponse):
    """
    Internal schema for service-layer use only.
    Extend here if the DB row ever gains sensitive/internal columns
    that must NOT be exposed via API.
    """
    pass


# ---------------------------------------------------------------------------
# Schema: VideoPublic  (safe minimal projection for embedding in other responses)
# ---------------------------------------------------------------------------

class VideoPublic(_VideoBase):
    """
    Minimal public projection of a video — safe to embed inside
    an Ask Video response without leaking user_id ownership details.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    status: VideoStatus