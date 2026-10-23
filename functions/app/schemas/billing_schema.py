import uuid
from typing import Literal

from pydantic import BaseModel, Field


class PackResponse(BaseModel):
    code: str
    credits: int
    amount_cents: int
    currency: str


class OrderRequest(BaseModel):
    pack_code: Literal["topup", "starter", "pro"]


class OrderResponse(BaseModel):
    """Everything the browser passes to Razorpay Checkout."""
    payment_id: uuid.UUID
    order_id: str
    key_id: str
    amount_cents: int
    currency: str
    credits: int


class VerifyRequest(BaseModel):
    # Field names as Razorpay Checkout returns them.
    razorpay_order_id: str = Field(min_length=1, max_length=100)
    razorpay_payment_id: str = Field(min_length=1, max_length=100)
    razorpay_signature: str = Field(min_length=1, max_length=200)


class VerifyResponse(BaseModel):
    payment_id: uuid.UUID
    # "created" means not captured yet; the webhook credits it shortly.
    status: Literal["created", "paid", "failed", "refunded", "disputed"]
    credits: int
