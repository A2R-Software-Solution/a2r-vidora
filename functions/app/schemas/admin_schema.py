import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CreditAdjustRequest(BaseModel):
    # Whole credits, positive to grant and negative to take back.
    amount: int = Field(..., ge=-100_000, le=100_000)
    reason: str = Field(..., min_length=3, max_length=180)

    @field_validator("amount")
    @classmethod
    def not_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("amount must not be zero")
        return v


class BanRequest(BaseModel):
    # Shown to the user, so write it for them.
    reason: str = Field(..., min_length=3, max_length=300)

    @field_validator("reason")
    @classmethod
    def tidy(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("reason is too short")
        return v


class SettingsUpdateRequest(BaseModel):
    # Setting key -> new value; null resets the setting to its default.
    values: dict[str, int | None] = Field(..., min_length=1, max_length=50)


class CreditAdjustResponse(BaseModel):
    user_id: uuid.UUID
    purchased_balance: int


PackCode = Literal["topup", "starter", "pro"]


class CouponUpdate(BaseModel):
    """Fields left out stay as they are."""
    percent_off: int | None = Field(None, ge=0, le=100)
    bonus_credits: int | None = Field(None, ge=0, le=100_000)
    # None or an empty list: every pack.
    packs: list[PackCode] | None = None
    # None: both currencies.
    currency: Literal["USD", "INR"] | None = None
    # None: no limit.
    max_uses: int | None = Field(None, ge=1, le=1_000_000)
    per_user_limit: int | None = Field(None, ge=1, le=1000)
    expires_at: datetime | None = None
    active: bool | None = None
    note: str | None = Field(None, max_length=200)

    @field_validator("percent_off", "bonus_credits", "active")
    @classmethod
    def not_null(cls, v):
        if v is None:
            raise ValueError("must not be null")
        return v


class CouponCreate(CouponUpdate):
    code: str = Field(..., min_length=3, max_length=40)
    percent_off: int = Field(0, ge=0, le=100)
    bonus_credits: int = Field(0, ge=0, le=100_000)
    per_user_limit: int | None = Field(1, ge=1, le=1000)
    active: bool = True
