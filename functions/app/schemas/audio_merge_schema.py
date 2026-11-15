import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from app.core.config import settings
from app.utils.youtube import extract_youtube_id

MAX_FADE_SECONDS = 10
MIN_TRACK_SECONDS = 0.1


class TrackRequest(BaseModel):
    """One section of a source. Uploaded tracks name their file by its position
    in the request's `files` list."""
    source: Literal["youtube", "upload"]
    url: str | None = Field(default=None, max_length=500)
    file_index: int | None = Field(default=None, ge=0, strict=True)
    # Seconds; whole numbers or decimals down to a millisecond.
    start_time: float = Field(ge=0, strict=True, allow_inf_nan=False)
    end_time: float = Field(gt=0, strict=True, allow_inf_nan=False)
    # Pro editor: loudness in percent, and fades in seconds at the section's edges.
    volume: int = Field(default=100, ge=0, le=100, strict=True)
    fade_in: int = Field(default=0, ge=0, le=MAX_FADE_SECONDS, strict=True)
    fade_out: int = Field(default=0, ge=0, le=MAX_FADE_SECONDS, strict=True)
    # A YouTube track already loaded in the Pro editor; its stored audio is used when still available.
    source_id: uuid.UUID | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def to_milliseconds(cls, value: float) -> float:
        return round(value, 3)

    @model_validator(mode="after")
    def validate_track(self):
        if self.source == "youtube":
            if not self.url:
                raise ValueError("A YouTube track needs a url.")
            extract_youtube_id(self.url)
            if self.file_index is not None:
                raise ValueError("A YouTube track cannot reference an uploaded file.")
        else:
            if self.file_index is None:
                raise ValueError("An uploaded track needs a file_index.")
            if self.url is not None:
                raise ValueError("An uploaded track cannot have a url.")
            if self.source_id is not None:
                raise ValueError("An uploaded track cannot reference a loaded song.")
        length = self.seconds
        if length <= 0:
            raise ValueError("A track must end after it starts.")
        if length < MIN_TRACK_SECONDS:
            raise ValueError(f"A track must be at least {MIN_TRACK_SECONDS} seconds long.")
        if length > settings.audio_merge_max_segment_seconds:
            raise ValueError(f"A track can be at most {settings.audio_merge_max_segment_seconds // 60} minutes long.")
        if self.fade_in + self.fade_out > length:
            raise ValueError("A track's fades cannot be longer than the track.")
        return self

    @property
    def seconds(self) -> float:
        return round(self.end_time - self.start_time, 3)


class AudioMergeRequest(BaseModel):
    tracks: list[TrackRequest] = Field(min_length=2)
    output_format: Literal["mp3", "m4a"] = "mp3"
    crossfade_seconds: int = Field(default=0, ge=0, le=10, strict=True)

    @model_validator(mode="after")
    def validate_merge(self):
        if len(self.tracks) > settings.audio_merge_max_tracks:
            raise ValueError(f"At most {settings.audio_merge_max_tracks} tracks can be merged.")
        if sum(track.seconds for track in self.tracks) > settings.audio_merge_max_total_seconds:
            raise ValueError(f"The merged audio can be at most {settings.audio_merge_max_total_seconds // 60} minutes long.")
        if self.crossfade_seconds and min(track.seconds for track in self.tracks) < self.crossfade_seconds * 2:
            raise ValueError("Every track must be at least twice as long as the crossfade.")
        return self


class AudioSourceRequest(BaseModel):
    url: str = Field(max_length=500)

    @model_validator(mode="after")
    def validate_url(self):
        extract_youtube_id(self.url)
        return self


class AudioSourceResponse(BaseModel):
    id: uuid.UUID
    video_id: str
    url: str
    title: str | None
    status: Literal["queued", "processing", "ready", "failed", "expired"]
    error_code: str | None
    duration_seconds: int | None
    peaks: list[int] | None
    preview_url: str | None
    expires_at: datetime


class TrackResponse(BaseModel):
    source: Literal["youtube", "upload"]
    url: str | None
    start_time: float
    end_time: float


class AudioMergeResponse(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "processing", "completed", "failed", "expired"]
    error_code: str | None
    output_format: str
    crossfade_seconds: int
    total_seconds: int
    credit_cost: int
    tracks: list[TrackResponse]
    created_at: datetime
    expires_at: datetime

    @classmethod
    def from_job(cls, job) -> "AudioMergeResponse":
        return cls(
            id=job.id, status=job.status, error_code=job.error_code, output_format=job.output_format,
            crossfade_seconds=job.crossfade_seconds, total_seconds=job.total_seconds,
            credit_cost=job.credit_cost, created_at=job.created_at, expires_at=job.expires_at,
            tracks=[TrackResponse(source=t["source"], url=t.get("url"),
                                  start_time=t["start_time"], end_time=t["end_time"]) for t in job.tracks])
