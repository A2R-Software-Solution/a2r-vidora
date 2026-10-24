import uuid

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


class CreditAdjustResponse(BaseModel):
    user_id: uuid.UUID
    purchased_balance: int
