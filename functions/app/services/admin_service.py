"""Read-mostly queries for the admin panel. Rows are returned as plain dicts."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.credit_model import CreditAccount, CreditLedgerEntry, Payment
from app.models.qa_log_model import QALog
from app.models.short_model import Short
from app.models.user_model import User
from app.models.video_model import Video, VideoStatus
from app.services.credit_service import CreditService


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _scalar(self, stmt) -> int:
        return int((await self.db.execute(stmt)).scalar_one() or 0)

    async def overview(self) -> dict:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        by_status = {s: c for s, c in (await self.db.execute(
            select(cast(Video.status, String), func.count()).group_by(Video.status))).all()}
        failed_stages = (await self.db.execute(
            select(Video.processing_stage, func.count()).where(
                Video.status == VideoStatus.FAILED, Video.created_at >= since)
            .group_by(Video.processing_stage).order_by(func.count().desc()).limit(10))).all()
        paid = (await self.db.execute(
            select(func.count(), func.coalesce(func.sum(Payment.amount_cents), 0))
            .where(Payment.status == "paid"))).one()
        paid_24h = (await self.db.execute(
            select(func.count(), func.coalesce(func.sum(Payment.amount_cents), 0))
            .where(Payment.status == "paid", Payment.paid_at >= since))).one()
        # Reserve rows are negative and release rows positive, so -sum is net spend.
        spent_24h = await self._scalar(
            select(func.coalesce(-func.sum(CreditLedgerEntry.amount), 0)).where(
                CreditLedgerEntry.kind.in_(("reserve", "release")), CreditLedgerEntry.created_at >= since))
        stt_seconds = int((await self.db.execute(
            text("SELECT COALESCE(SUM(audio_seconds), 0) FROM stt_quota_reservations WHERE reserved_at > :since"),
            {"since": since})).scalar_one())
        return {
            "users_total": await self._scalar(select(func.count()).select_from(User)),
            "users_24h": await self._scalar(select(func.count()).select_from(User).where(User.created_at >= since)),
            "videos_by_status": by_status,
            "videos_24h": await self._scalar(select(func.count()).select_from(Video).where(Video.created_at >= since)),
            "failures_24h_by_stage": [{"stage": s, "count": c} for s, c in failed_stages],
            "payments_paid": paid[0], "revenue_cents": int(paid[1]),
            "payments_paid_24h": paid_24h[0], "revenue_cents_24h": int(paid_24h[1]),
            "credits_outstanding": await self._scalar(
                select(func.coalesce(func.sum(CreditAccount.purchased_balance), 0))),
            "credits_spent_24h": spent_24h,
            "stt_seconds_24h": stt_seconds,
            "stt_seconds_limit_day": settings.stt_audio_seconds_per_day,
            "shorts_24h": await self._scalar(select(func.count()).select_from(Short).where(Short.created_at >= since)),
        }

    async def users(self, q: str | None, limit: int, offset: int) -> list[dict]:
        stmt = (select(User, CreditAccount.purchased_balance)
                .outerjoin(CreditAccount, CreditAccount.user_id == User.id)
                .order_by(User.created_at.desc()).limit(limit).offset(offset))
        if q:
            stmt = stmt.where(or_(User.email.ilike(_like(q), escape="\\"), cast(User.id, String) == q))
        return [{"id": u.id, "email": u.email, "plan": u.plan, "is_admin": u.is_admin,
                 "purchased_balance": balance or 0, "created_at": u.created_at}
                for u, balance in (await self.db.execute(stmt)).all()]

    async def user_detail(self, user_id: uuid.UUID) -> dict | None:
        user = (await self.db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            return None
        account = (await self.db.execute(
            select(CreditAccount).where(CreditAccount.user_id == user_id))).scalar_one_or_none()
        ledger = []
        if account is not None:
            ledger = (await self.db.execute(
                select(CreditLedgerEntry).where(CreditLedgerEntry.account_id == account.id)
                .order_by(CreditLedgerEntry.created_at.desc()).limit(50))).scalars().all()
        payments = (await self.db.execute(
            select(Payment).where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc()).limit(20))).scalars().all()
        videos = (await self.db.execute(
            select(Video).where(Video.user_id == user_id)
            .order_by(Video.created_at.desc()).limit(20))).scalars().all()
        return {
            "id": user.id, "email": user.email, "plan": user.plan, "is_admin": user.is_admin,
            "created_at": user.created_at,
            "account": None if account is None else {
                "purchased_balance": account.purchased_balance, "daily_free_used": account.daily_free_used,
                "daily_chat_used": account.daily_chat_used, "daily_date": account.daily_date},
            "ledger": [{"id": e.id, "kind": e.kind, "bucket": e.bucket, "amount": e.amount,
                        "balance_after": e.purchased_balance_after, "note": e.note,
                        "created_at": e.created_at} for e in ledger],
            "payments": [self._payment(p) for p in payments],
            "videos": [self._video(v) for v in videos],
        }

    async def adjust_credits(self, user_id: uuid.UUID, amount: int, reason: str, admin_email: str) -> int | None:
        if (await self.db.execute(select(User.id).where(User.id == user_id))).scalar_one_or_none() is None:
            return None
        return await CreditService(self.db).adjust(user_id, amount, note=f"admin:{admin_email}: {reason}")

    @staticmethod
    def _payment(p: Payment) -> dict:
        return {"id": p.id, "user_id": p.user_id, "pack_code": p.pack_code, "credits": p.credits,
                "amount_cents": p.amount_cents, "currency": p.currency, "provider": p.provider,
                "provider_order_id": p.provider_order_id, "provider_payment_id": p.provider_payment_id,
                "status": p.status, "created_at": p.created_at, "paid_at": p.paid_at}

    @staticmethod
    def _video(v: Video) -> dict:
        return {"id": v.id, "user_id": v.user_id, "youtube_url": v.youtube_url, "title": v.title,
                "duration": v.duration, "status": v.status.value, "processing_stage": v.processing_stage,
                "priority": v.priority, "is_guest": v.user_id is None, "created_at": v.created_at,
                "expires_at": v.expires_at}

    async def payments(self, status: str | None, limit: int, offset: int) -> list[dict]:
        stmt = (select(Payment, User.email).join(User, User.id == Payment.user_id)
                .order_by(Payment.created_at.desc()).limit(limit).offset(offset))
        if status:
            stmt = stmt.where(Payment.status == status)
        return [{**self._payment(p), "email": email} for p, email in (await self.db.execute(stmt)).all()]

    async def videos(self, status: str | None, q: str | None, limit: int, offset: int) -> list[dict]:
        stmt = select(Video).order_by(Video.created_at.desc()).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(cast(Video.status, String) == status)
        if q:
            stmt = stmt.where(or_(Video.title.ilike(_like(q), escape="\\"),
                                  Video.youtube_url.ilike(_like(q), escape="\\")))
        return [self._video(v) for v in (await self.db.execute(stmt)).scalars().all()]

    async def shorts(self, status: str | None, limit: int, offset: int) -> list[dict]:
        stmt = select(Short).order_by(Short.created_at.desc()).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(Short.status == status)
        return [{"id": s.id, "video_id": s.video_id, "start_time": s.start_time, "end_time": s.end_time,
                 "status": s.status, "error_code": s.error_code, "created_at": s.created_at,
                 "expires_at": s.expires_at} for s in (await self.db.execute(stmt)).scalars().all()]

    async def qa_logs(self, q: str | None, limit: int, offset: int) -> list[dict]:
        stmt = (select(QALog, User.email).outerjoin(User, User.id == QALog.user_id)
                .order_by(QALog.created_at.desc()).limit(limit).offset(offset))
        if q:
            stmt = stmt.where(or_(QALog.question.ilike(_like(q), escape="\\"),
                                  QALog.answer.ilike(_like(q), escape="\\")))
        return [{"id": log.id, "video_id": log.video_id, "email": email, "question": log.question,
                 "answer": log.answer, "created_at": log.created_at}
                for log, email in (await self.db.execute(stmt)).all()]
