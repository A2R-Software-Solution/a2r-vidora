"""Read-mostly queries for the admin panel. Rows are returned as plain dicts."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import String, cast, extract, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.app_setting_model import AppSetting
from app.models.credit_model import CreditAccount, CreditLedgerEntry, Payment
from app.models.qa_log_model import QALog
from app.models.short_model import Short
from app.models.user_model import User
from app.models.video_model import Video, VideoStatus
from app.services.credit_service import IST, CreditService, ist_today, month_start


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class AdminBanError(Exception):
    """The ban is not allowed (for example, the target is an admin)."""


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

    async def credits_summary(self) -> dict:
        """Credits given to and used by signed-in users, this IST month and all time.

        Free credits are a lazily reset monthly allowance with no ledger row, so
        "free given" is users x the current allowance (an estimate for past
        months if the allowance changed). Everything else comes from the ledger.
        """
        now = datetime.now(timezone.utc)
        month_begin = datetime.combine(month_start(ist_today(now)), time.min, tzinfo=IST)
        allowance = settings.user_monthly_credits
        ist_created = func.timezone("Asia/Kolkata", User.created_at)
        month_index = extract("year", ist_created) * 12 + extract("month", ist_created)
        user_months = await self._scalar(select(func.coalesce(
            func.sum((now.astimezone(IST).year * 12 + now.astimezone(IST).month) - month_index + 1), 0)))
        users_this_month = await self._scalar(select(func.count()).select_from(User).where(User.created_at <= now))

        async def window(since: datetime | None, free_given: int) -> dict:
            stmt = (select(CreditLedgerEntry.kind, CreditLedgerEntry.bucket,
                           func.sign(CreditLedgerEntry.amount), func.sum(CreditLedgerEntry.amount))
                    .join(CreditAccount, CreditAccount.id == CreditLedgerEntry.account_id)
                    .where(CreditAccount.user_id.is_not(None))
                    .group_by(CreditLedgerEntry.kind, CreditLedgerEntry.bucket, func.sign(CreditLedgerEntry.amount)))
            if since is not None:
                stmt = stmt.where(CreditLedgerEntry.created_at >= since)
            totals: dict[tuple, int] = {}
            for kind, bucket, sign, amount in (await self.db.execute(stmt)).all():
                totals[(kind, bucket, int(sign))] = totals.get((kind, bucket, int(sign)), 0) + int(amount or 0)

            def total(kind: str, bucket: str | None = None, sign: int | None = None) -> int:
                return sum(v for (k, b, s), v in totals.items()
                           if k == kind and bucket in (None, b) and sign in (None, s))

            # Reserve rows are negative and release (refund of a failed job) rows positive.
            free_used = -(total("reserve", "free") + total("release", "free"))
            purchased_used = -(total("reserve", "purchased") + total("release", "purchased"))
            purchased_given = total("purchase")
            admin_added = total("adjust", sign=1)
            given = free_given + purchased_given + admin_added
            used = free_used + purchased_used
            return {
                "free_given": free_given, "purchased_given": purchased_given, "admin_added": admin_added,
                "total_given": given, "free_used": free_used, "purchased_used": purchased_used,
                "total_used": used, "taken_back": -(total("adjust", sign=-1) + total("refund")),
                "used_percent": round(used * 100 / given, 1) if given else None,
            }

        # Paid packs per IST month, newest first; a refunded or disputed payment is no longer a sale.
        paid_month = func.date_trunc("month", func.timezone("Asia/Kolkata", Payment.paid_at))
        sales = (await self.db.execute(
            select(paid_month, func.count(), func.sum(Payment.credits), func.sum(Payment.amount_cents))
            .where(Payment.status == "paid", Payment.paid_at.is_not(None))
            .group_by(paid_month).order_by(paid_month.desc()).limit(12))).all()

        return {
            "sales_by_month": [{"month": m.date().isoformat(), "payments": int(n), "credits_sold": int(c or 0),
                                "revenue_cents": int(r or 0)} for m, n, c, r in sales],
            "free_allowance_per_user": allowance,
            "month_start": month_begin.date().isoformat(),
            "this_month": await window(month_begin, users_this_month * allowance),
            "all_time": await window(None, user_months * allowance),
            "purchased_outstanding": await self._scalar(
                select(func.coalesce(func.sum(CreditAccount.purchased_balance), 0))
                .where(CreditAccount.user_id.is_not(None))),
        }

    async def users(self, q: str | None, limit: int, offset: int) -> list[dict]:
        stmt = (select(User, CreditAccount.purchased_balance, CreditAccount.free_used, CreditAccount.free_month)
                .outerjoin(CreditAccount, CreditAccount.user_id == User.id)
                .order_by(User.created_at.desc()).limit(limit).offset(offset))
        if q:
            stmt = stmt.where(or_(User.email.ilike(_like(q), escape="\\"), cast(User.id, String) == q))
        return [self._user_row(u, balance, free_used, free_month)
                for u, balance, free_used, free_month in (await self.db.execute(stmt)).all()]

    async def timeseries(self, days: int) -> dict:
        """Per-day counts for the last `days` days (UTC), zeros included, for the dashboard charts."""
        today = datetime.now(timezone.utc).date()
        first = today - timedelta(days=days - 1)
        since = datetime.combine(first, time.min, tzinfo=timezone.utc)
        labels = [first + timedelta(days=i) for i in range(days)]

        async def per_day(column, value, *conditions) -> list[int]:
            day = func.date(func.timezone("UTC", column))
            rows = (await self.db.execute(
                select(day, value).where(column >= since, *conditions).group_by(day))).all()
            found = {row[0]: int(row[1] or 0) for row in rows}
            return [found.get(label, 0) for label in labels]

        return {
            "days": [label.isoformat() for label in labels],
            "users": await per_day(User.created_at, func.count()),
            "videos": await per_day(Video.created_at, func.count()),
            "shorts": await per_day(Short.created_at, func.count()),
            "revenue_cents": await per_day(Payment.paid_at, func.sum(Payment.amount_cents), Payment.status == "paid"),
            # Reserve rows are negative and release rows positive: -sum is net spend.
            "credits_spent": await per_day(CreditLedgerEntry.created_at, -func.sum(CreditLedgerEntry.amount),
                                           CreditLedgerEntry.kind.in_(("reserve", "release"))),
        }

    async def activity(self, limit: int) -> list[dict]:
        """The latest things that happened on the platform, newest first."""
        events: list[dict] = []

        async def rows(stmt):
            return (await self.db.execute(stmt.limit(limit))).all()

        for email, at in await rows(select(User.email, User.created_at).order_by(User.created_at.desc())):
            events.append({"type": "user", "title": "New user registered", "detail": email, "at": at})
        for status, at in await rows(select(Short.status, Short.created_at).order_by(Short.created_at.desc())):
            events.append({"type": "short", "title": "New reel created", "detail": status, "at": at})
        for title, url, at in await rows(select(Video.title, Video.youtube_url, Video.created_at).order_by(Video.created_at.desc())):
            events.append({"type": "video", "title": "Video analysed", "detail": title or url, "at": at})
        for kind, amount, email, at in await rows(
                select(CreditLedgerEntry.kind, CreditLedgerEntry.amount, User.email, CreditLedgerEntry.created_at)
                .join(CreditAccount, CreditAccount.id == CreditLedgerEntry.account_id)
                .outerjoin(User, User.id == CreditAccount.user_id)
                .where(CreditLedgerEntry.kind.in_(("adjust", "purchase")))
                .order_by(CreditLedgerEntry.created_at.desc())):
            word = "purchased" if kind == "purchase" else ("added" if amount > 0 else "removed")
            events.append({"type": "credits", "title": f"Credits {word} ({abs(amount)})", "detail": email, "at": at})
        for key, by, at in await rows(select(AppSetting.key, AppSetting.updated_by, AppSetting.updated_at)
                                      .order_by(AppSetting.updated_at.desc())):
            events.append({"type": "settings", "title": "Settings updated", "detail": f"{key} by {by}", "at": at})
        events.sort(key=lambda event: event["at"], reverse=True)
        return events[:limit]

    @staticmethod
    def _user_row(u: User, balance, free_used, free_month) -> dict:
        """Purchased credits plus what is left of this month's free allowance."""
        purchased = balance or 0
        monthly = settings.user_monthly_credits
        used = free_used if free_month == month_start(ist_today()) and free_used else 0
        free_left = max(monthly - used, 0)
        return {"id": u.id, "email": u.email, "plan": u.plan, "is_admin": u.is_admin,
                "purchased_balance": purchased, "free_left": free_left, "available": purchased + free_left,
                "banned": u.banned_at is not None, "ban_reason": u.ban_reason, "created_at": u.created_at}

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
            "banned": user.banned_at is not None, "banned_at": user.banned_at, "ban_reason": user.ban_reason,
            "created_at": user.created_at,
            "account": None if account is None else {
                "purchased_balance": account.purchased_balance, "free_used": account.free_used, "free_month": account.free_month,
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

    async def ban(self, user_id: uuid.UUID, reason: str, admin: User) -> bool:
        """Bans the user and stores the message they will see. False if there is no such user."""
        user = (await self.db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
        if user is None:
            return False
        if user.is_admin or user.id == admin.id:
            raise AdminBanError("Admins cannot be banned.")
        user.banned_at = datetime.now(timezone.utc)
        user.ban_reason = reason
        await self.db.commit()
        return True

    async def unban(self, user_id: uuid.UUID) -> bool:
        user = (await self.db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
        if user is None:
            return False
        user.banned_at = None
        user.ban_reason = None
        await self.db.commit()
        return True

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
