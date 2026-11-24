"""Coupon codes: validation at checkout and management from the admin panel.

A coupon lowers a pack's price by a percentage, adds bonus credits, or both.
Its effect is copied onto the Payment when the order is created, so editing
or deactivating a coupon never changes a past purchase. A use counts once the
payment is paid; an unpaid order holds its use for PENDING_HOLD, so two quick
checkouts cannot both take the last use.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coupon_model import Coupon
from app.models.credit_model import Payment

# Razorpay's smallest order is 1 INR / 1 USD-equivalent; a coupon never goes below 100 units.
MIN_AMOUNT = 100
PENDING_HOLD = timedelta(minutes=30)
CODE_PATTERN = re.compile(r"^[A-Z0-9_-]{3,40}$")


class CouponError(ValueError):
    """The coupon cannot be used. The message is safe to show the buyer."""


@dataclass(frozen=True)
class CouponPrice:
    amount: int
    credits: int


def normalize_code(code: str) -> str:
    return code.strip().upper()


def discounted(amount: int, credits: int, coupon: Coupon) -> CouponPrice:
    """The pack's price and credits after the coupon. The price never drops
    below MIN_AMOUNT (or the original price, if that is already lower)."""
    # Half up, the same as Math.round on the pricing page.
    price = (amount * (100 - coupon.percent_off) + 50) // 100
    return CouponPrice(amount=max(price, min(amount, MIN_AMOUNT)), credits=credits + coupon.bonus_credits)


def pack_codes(coupon: Coupon) -> list[str] | None:
    return coupon.packs.split(",") if coupon.packs else None


def coupon_problem(coupon: Coupon | None, *, now: datetime, currency: str, pack_code: str | None,
                   used_total: int, used_by_user: int) -> str | None:
    """Why the coupon cannot be used, or None when it can."""
    if coupon is None or not coupon.active:
        return "This coupon code is not valid."
    if coupon.expires_at is not None and coupon.expires_at <= now:
        return "This coupon has expired."
    if coupon.currency is not None and coupon.currency != currency:
        return f"This coupon is not valid for payments in {currency}."
    packs = pack_codes(coupon)
    if pack_code is not None and packs is not None and pack_code not in packs:
        return "This coupon does not apply to this pack."
    if coupon.max_uses is not None and used_total >= coupon.max_uses:
        return "This coupon has been used up."
    if coupon.per_user_limit is not None and used_by_user >= coupon.per_user_limit:
        return "You have already used this coupon."
    return None


def _counts_as_use(now: datetime):
    """A paid payment, or an unpaid order still within PENDING_HOLD."""
    return or_(Payment.status == "paid",
               and_(Payment.status == "created", Payment.created_at > now - PENDING_HOLD))


class CouponService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _usage(self, coupon_id: uuid.UUID, user_id: uuid.UUID, now: datetime) -> tuple[int, int]:
        rows = (await self.db.execute(
            select(Payment.user_id, func.count()).where(Payment.coupon_id == coupon_id, _counts_as_use(now))
            .group_by(Payment.user_id))).all()
        return sum(n for _, n in rows), sum(n for uid, n in rows if uid == user_id)

    async def usable(self, code: str, *, user_id: uuid.UUID, currency: str,
                     pack_code: str | None = None, lock: bool = False) -> Coupon:
        """The coupon for this buyer, or CouponError. lock=True holds the
        coupon row until the caller commits, so its use count cannot race."""
        stmt = select(Coupon).where(Coupon.code == normalize_code(code))
        if lock:
            stmt = stmt.with_for_update()
        coupon = (await self.db.execute(stmt)).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        used_total, used_by_user = (await self._usage(coupon.id, user_id, now)) if coupon else (0, 0)
        problem = coupon_problem(coupon, now=now, currency=currency, pack_code=pack_code,
                                 used_total=used_total, used_by_user=used_by_user)
        if problem:
            raise CouponError(problem)
        return coupon

    # Admin panel

    async def list(self) -> list[dict]:
        """Every coupon with its paid uses and revenue (in each payment's own currency)."""
        coupons = (await self.db.execute(select(Coupon).order_by(Coupon.created_at.desc()))).scalars().all()
        stats = (await self.db.execute(
            select(Payment.coupon_id, Payment.currency, func.count(), func.sum(Payment.amount_cents))
            .where(Payment.coupon_id.is_not(None), Payment.status == "paid")
            .group_by(Payment.coupon_id, Payment.currency))).all()
        uses: dict[uuid.UUID, int] = {}
        revenue: dict[uuid.UUID, dict[str, int]] = {}
        for coupon_id, currency, count, total in stats:
            uses[coupon_id] = uses.get(coupon_id, 0) + count
            revenue.setdefault(coupon_id, {})[currency] = int(total or 0)
        return [{**self.row(c), "uses": uses.get(c.id, 0), "revenue": revenue.get(c.id, {})} for c in coupons]

    async def create(self, data: dict, *, admin_email: str) -> Coupon:
        code = normalize_code(data["code"])
        if not CODE_PATTERN.match(code):
            raise CouponError("Use 3–40 letters, numbers, - or _ for the code.")
        if (await self.db.execute(select(Coupon.id).where(Coupon.code == code))).first():
            raise CouponError("A coupon with this code already exists.")
        coupon = Coupon(id=uuid.uuid4(), code=code, created_by=admin_email, **self._fields(data))
        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)
        return coupon

    async def update(self, coupon_id: uuid.UUID, data: dict) -> Coupon:
        coupon = await self.db.get(Coupon, coupon_id)
        if coupon is None:
            raise LookupError(coupon_id)
        for key, value in self._fields(data).items():
            setattr(coupon, key, value)
        if coupon.percent_off == 0 and coupon.bonus_credits == 0:
            await self.db.rollback()
            raise CouponError("Give the coupon a discount, bonus credits, or both.")
        await self.db.commit()
        await self.db.refresh(coupon)
        return coupon

    @staticmethod
    def _fields(data: dict) -> dict:
        fields = {key: data[key] for key in ("percent_off", "bonus_credits", "currency", "max_uses",
                                              "per_user_limit", "expires_at", "active", "note") if key in data}
        if "packs" in data:
            fields["packs"] = ",".join(data["packs"]) if data["packs"] else None
        if fields.get("percent_off", 1) == 0 and fields.get("bonus_credits", 1) == 0:
            raise CouponError("Give the coupon a discount, bonus credits, or both.")
        return fields

    @staticmethod
    def row(c: Coupon) -> dict:
        return {"id": c.id, "code": c.code, "percent_off": c.percent_off, "bonus_credits": c.bonus_credits,
                "packs": pack_codes(c), "currency": c.currency, "max_uses": c.max_uses,
                "per_user_limit": c.per_user_limit, "expires_at": c.expires_at, "active": c.active,
                "note": c.note, "created_by": c.created_by, "created_at": c.created_at}
