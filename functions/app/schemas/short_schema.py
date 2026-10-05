import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ShortRequest(BaseModel):
    start_time: int = Field(ge=0, strict=True)
    end_time: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def validate_range(self):
        if not 20 <= self.end_time - self.start_time <= 60:
            raise ValueError("A Short must be 20 to 60 seconds long.")
        return self


class ShortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    video_id: uuid.UUID
    start_time: int
    end_time: int
    status: Literal["queued", "rendering", "completed", "failed", "expired"]
    error_code: str | None
    created_at: datetime
    expires_at: datetime
