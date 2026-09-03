from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAX_QUESTION_LEN: int = 2000  # abuse guard before hitting the embedding model


class _QALogBase(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        str_min_length=1,
        frozen=False,
    )

class QuestionRequest(_QALogBase):
    """
    Payload the client sends to ask a question about a video.
    Everything else needed to build a QALog row (answer, video_id
    association, user_id, created_at) is filled in server-side.
    """

    question: str = Field(
        ...,
        max_length=_MAX_QUESTION_LEN,
        description="Natural-language question about the video.",
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be empty or whitespace-only.")
        return v


class QALogCreate(_QALogBase):
    """
    Internal payload used to persist a Q&A exchange once the full
    retrieval -> Groq round trip has completed successfully.
    """

    video_id: uuid.UUID = Field(
        ...,
        description="Video this exchange belongs to, set server-side.",
    )
    user_id: uuid.UUID | None = Field(
        default=None,
        description="Owning user, null for anonymous requests.",
    )
    question: str = Field(..., max_length=_MAX_QUESTION_LEN)
    answer: str = Field(..., description="Groq-generated answer text.")

    @field_validator("question", "answer")
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field must not be empty or whitespace-only.")
        return v


class QALogResponse(_QALogBase):
    """
    Read-only schema returned from API responses.
    user_id is only ever populated for the owning user's own request
    context — cross-user log access is an authorization concern handled
    at the route/service layer, not by this schema.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Primary key (UUID v4).")
    video_id: uuid.UUID = Field(..., description="Associated video id.")
    user_id: uuid.UUID | None = Field(..., description="Owning user, null if anonymous.")
    question: str = Field(..., description="Question as asked.")
    answer: str = Field(..., description="Generated answer.")
    created_at: datetime = Field(..., description="UTC timestamp of the exchange.")



class QALogInDB(QALogResponse):
    """
    Internal schema for service-layer use only.
    Extend here if the row ever gains sensitive/internal columns
    that must NOT be exposed via API.
    """
    pass