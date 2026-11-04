import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import parse_qs, urlparse
from pydantic import BaseModel, Field, field_validator
from app.pipeline.media_formats import QUALITIES
from app.utils.youtube import extract_youtube_id


def normalize_media_url(url: str) -> str:
    """Accepts watch, youtu.be and Shorts links; returns the canonical watch URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme == "https" and parsed.netloc.lower() in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else ""
            url = f"https://www.youtube.com/watch?v={video_id}"
    return f"https://www.youtube.com/watch?v={extract_youtube_id(url)}"


class PreviewRequest(BaseModel):
    url: str = Field(max_length=500)

    @field_validator("url")
    @classmethod
    def _youtube_only(cls, value: str) -> str:
        return normalize_media_url(value)


class DownloadRequest(BaseModel):
    url: str = Field(max_length=500)
    quality: str = Field(max_length=16)
    # Must be true to download: the requester confirms the content is their own.
    rights_confirmed: Literal[True]

    @field_validator("url")
    @classmethod
    def _youtube_only(cls, value: str) -> str:
        return normalize_media_url(value)

    @field_validator("quality")
    @classmethod
    def _known_quality(cls, value: str) -> str:
        if value not in QUALITIES:
            raise ValueError("Unknown quality.")
        if not QUALITIES[value].available:
            raise ValueError("This quality is not available yet.")
        return value


class DownloadResponse(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "processing", "completed", "failed", "expired"]
    error_code: str | None
    title: str | None
    quality: str
    duration_seconds: int
    credit_cost: int
    created_at: datetime
    expires_at: datetime

    @classmethod
    def from_job(cls, job) -> "DownloadResponse":
        return cls(
            id=job.id, status=job.status, error_code=job.error_code, title=job.title,
            quality=job.quality, duration_seconds=job.duration_seconds, credit_cost=job.credit_cost,
            created_at=job.created_at, expires_at=job.expires_at,
        )
