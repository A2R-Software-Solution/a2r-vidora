from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

_PLAN_OPTIONS = Literal["free", "pro", "enterprise"]

_EMAIL_MAX_LEN: int = 250
_PLAN_MAX_LEN: int = 250

# Firebase UID pattern: alphanumeric + underscores/hyphens, 20-128 chars
_FIREBASE_UID_RE = re.compile(r"^[a-zA-Z0-9_\-]{20,128}$")

class _UserBase(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        str_min_length=1,
        frozen=False,
    )

class UserCreate(_UserBase):
    """
    Payload required to create a new user record.
    `firebase_uid` and `email` come from the verified Firebase ID token
    on the backend — validated here before DB insert.
    """

    firebase_uid: str = Field(
        ...,
        description="Firebase UID extracted from the ID token.",
        min_length=20,
        max_length=128,
    )
    email: EmailStr = Field(
        ...,
        description="Verified email from Firebase auth.",
    )
    plan: _PLAN_OPTIONS = Field(
        default="free",
        description="Subscription plan. Defaults to 'free' on signup.",
    )

    @field_validator("firebase_uid")
    @classmethod
    def validate_firebase_uid(cls, v: str) -> str:
        if not _FIREBASE_UID_RE.match(v):
            raise ValueError(
                "firebase_uid must be 20-128 alphanumeric characters "
                "(underscores and hyphens allowed)."
            )
        return v

    @field_validator("email")
    @classmethod
    def validate_email_length(cls, v: str) -> str:
        if len(v) > _EMAIL_MAX_LEN:
            raise ValueError(f"email must not exceed {_EMAIL_MAX_LEN} characters.")
        return v.lower()


class UserUpdate(_UserBase):
    """
    Partial update payload for an existing user.
    Only `plan` is updatable via the API — firebase_uid and email
    are immutable after creation.
    """

    plan: _PLAN_OPTIONS | None = Field(
        default=None,
        description="New subscription plan.",
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdate":
        if all(v is None for v in self.model_dump().values()):
            raise ValueError("At least one field must be provided for update.")
        return self


class UserResponse(_UserBase):
    """
    Read-only schema returned from API responses.
    Maps directly to the DB row.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Primary key (UUID v4).")
    firebase_uid: str = Field(..., description="Firebase UID.")
    email: EmailStr = Field(..., description="User's email address.")
    plan: str = Field(..., description="Current subscription plan.")
    created_at: datetime = Field(..., description="UTC timestamp of account creation.")


class UserInDB(UserResponse):
    """
    Internal schema for service-layer use only.
    Extend here if the DB row ever gains sensitive/internal columns
    that must NOT be exposed via API.
    """
    pass



class UserPublic(_UserBase):
    """
    Minimal public projection of a user — safe to embed inside
    video/chat responses without leaking firebase_uid or plan details.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    plan: str