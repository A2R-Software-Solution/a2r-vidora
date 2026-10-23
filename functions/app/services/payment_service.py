"""Credit pack purchases through Razorpay.

A pack is credited exactly once, by whichever arrives first: the browser's
post-checkout verification or Razorpay's webhook. Both lock the payment row,
check the captured amount against the pack, and the ledger's unique index
backs that up. Refunds and disputes are started from the Razorpay dashboard;
their webhooks take back whatever credits of that pack are still unspent.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integration import razorpay_client
from app.middleware.logging import logger
from app.models.credit_model import Payment
from app.services.credit_service import CreditService


@dataclass(frozen=True)
class CreditPack:
    code: str
    credits: int
    amount_cents: int
    currency: str = "USD"


# Prices are copied onto each Payment at checkout, so changing them here
# never alters past purchases.
PACKS: dict[str, CreditPack] = {pack.code: pack for pack in (
    CreditPack("topup", credits=120, amount_cents=259),
    CreditPack("starter", credits=300, amount_cents=500),
    CreditPack("pro", credits=800, amount_cents=1000),
)}


class UnknownPackError(Exception):
    pass


class PaymentNotFoundError(Exception):
    pass


class InvalidPaymentSignatureError(Exception):
    pass


class PaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_order(self, user_id: uuid.UUID, pack_code: str) -> Payment:
        pack = PACKS.get(pack_code)
        if pack is None:
            raise UnknownPackError(pack_code)
        payment_id = uuid.uuid4()
        order = await razorpay_client.create_order(
            amount=pack.amount_cents, currency=pack.currency, receipt=str(payment_id),
            notes={"payment_id": str(payment_id), "user_id": str(user_id), "pack": pack.code},
        )
        # An order whose row fails to save is simply never paid; nothing to undo.
        payment = Payment(
            id=payment_id, user_id=user_id, pack_code=pack.code, credits=pack.credits,
            amount_cents=pack.amount_cents, currency=pack.currency, provider="razorpay",
            provider_order_id=order["id"], status="created",
        )
        self.db.add(payment)
        await self.db.commit()
        return payment

    async def _locked(self, *, order_id: str | None = None,
                      provider_payment_id: str | None = None) -> Payment | None:
        column, value = ((Payment.provider_order_id, order_id) if order_id
                         else (Payment.provider_payment_id, provider_payment_id))
        return (await self.db.execute(
            select(Payment).where(column == value).with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()

    async def _fulfil(self, entity: dict) -> Payment | None:
        """Credits a captured Razorpay payment entity once. Returns the
        Payment, or None when the order is not one of ours."""
        payment = await self._locked(order_id=entity.get("order_id"))
        if payment is None:
            await self.db.commit()
            return None
        if payment.status in {"paid", "refunded", "disputed"}:
            await self.db.commit()
            return payment
        if entity.get("status") != "captured":
            await self.db.commit()
            return payment
        if entity.get("amount") != payment.amount_cents or entity.get("currency") != payment.currency:
            # Never credit a pack for a different amount than its price.
            logger.error("payment_amount_mismatch payment_id=%s", payment.id)
            await self.db.commit()
            return payment
        payment.status = "paid"
        payment.provider_payment_id = entity["id"]
        payment.paid_at = datetime.now(timezone.utc)
        await CreditService(self.db, commit=False).grant_purchase(payment)
        await self.db.commit()
        logger.info("payment_credited payment_id=%s credits=%s", payment.id, payment.credits)
        return payment

    async def verify_checkout(self, user_id: uuid.UUID, *, order_id: str, payment_id: str,
                              signature: str) -> Payment:
        """Called by the browser right after checkout. Credits immediately when
        Razorpay reports the payment captured; otherwise the webhook will."""
        if not razorpay_client.checkout_signature_valid(order_id, payment_id, signature):
            raise InvalidPaymentSignatureError()
        payment = (await self.db.execute(select(Payment).where(
            Payment.provider_order_id == order_id))).scalar_one_or_none()
        if payment is None or payment.user_id != user_id:
            raise PaymentNotFoundError(order_id)
        entity = await razorpay_client.fetch_payment(payment_id)
        if entity.get("order_id") != order_id:
            raise InvalidPaymentSignatureError()
        return await self._fulfil(entity) or payment

    async def handle_webhook(self, event: dict) -> None:
        """Applies one verified webhook event. Unknown events are ignored."""
        name = event.get("event")
        payload = event.get("payload", {})
        if name in {"payment.captured", "order.paid"}:
            await self._fulfil(payload.get("payment", {}).get("entity", {}))
        elif name == "payment.failed":
            payment = await self._locked(order_id=payload.get("payment", {}).get("entity", {}).get("order_id"))
            if payment is not None and payment.status == "created":
                payment.status = "failed"
            await self.db.commit()
        elif name == "refund.processed":
            await self._take_back(payload.get("refund", {}).get("entity", {}).get("payment_id"), "refunded")
        elif name == "payment.dispute.created":
            await self._take_back(payload.get("dispute", {}).get("entity", {}).get("payment_id"), "disputed")

    async def _take_back(self, provider_payment_id: str | None, status: str) -> None:
        payment = await self._locked(provider_payment_id=provider_payment_id) if provider_payment_id else None
        if payment is None or payment.status != "paid":
            # Not ours, never credited, or already taken back.
            await self.db.commit()
            return
        payment.status = status
        taken = await CreditService(self.db, commit=False).revoke_purchase(payment, note=status)
        await self.db.commit()
        logger.info("payment_reversed payment_id=%s status=%s credits_taken=%s of=%s",
                    payment.id, status, taken, payment.credits)
