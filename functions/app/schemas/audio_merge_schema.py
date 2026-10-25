import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.core.config import settings
from app.utils.youtube import extract_youtube_id


class TrackRequest(BaseModel):
    """One section of a source. Uploaded tracks name their file by its position
    in the request's `files` list."""
    source: Literal["youtube", "upload"]
    url: str | None = Field(default=None, max_length=500)
    file_index: int | None = Field(default=None, ge=0, strict=True)
    start_time: int = Field(ge=0, strict=True)
    end_time: int = Field(gt=0, strict=True)

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
        length = self.end_time - self.start_time
        if length <= 0:
            raise ValueError("A track must end after it starts.")
        if length > settings.audio_merge_max_segment_seconds:
            raise ValueError(f"A track can be at most {settings.audio_merge_max_segment_seconds // 60} minutes long.")
        return self

    @property
    def seconds(self) -> int:
        return self.end_time - self.start_time


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
        uploads = [t.file_index for t in self.tracks if t.source == "upload"]
        if len(uploads) != len(set(uploads)):
            raise ValueError("Each uploaded file can be used by one track only.")
        return self


class TrackResponse(BaseModel):
    source: Literal["youtube", "upload"]
    url: str | None
    start_time: int
    end_time: int


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
