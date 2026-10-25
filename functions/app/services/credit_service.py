"""Credit wallets: daily free allowances, purchased balances and reservations.

A reservation deducts credits immediately (free allowance first, then the
purchased balance). It is later settled when the work succeeds, or released
back to the buckets it came from when the work fails on our side. Every
movement is written to the append-only credit ledger.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.credit_model import CreditAccount, CreditLedgerEntry, CreditReservation, Payment
from app.models.audio_merge_model import AudioMerge
from app.models.short_model import Short
from app.models.video_model import Video, VideoStatus

# IST has no daylight saving, so a fixed offset avoids depending on tzdata.
IST = timezone(timedelta(hours=5, minutes=30))

# Failures caused by the submitted content rather than by Vidora. Credits
# reserved for these are kept; every other failure is refunded.
USER_FAULT_REASONS = frozenset({"no_speech"})


class InsufficientCreditsError(Exception):
    def __init__(self, needed: int, available: int) -> None:
        super().__init__(f"{needed} credits needed, {available} available.")
        self.needed = needed
        self.available = available


class ReservationClosedError(Exception):
    """The key was already used by a reservation that has been refunded, so
    the work must not run again without a fresh reservation."""


class ChatLimitError(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"Daily question limit of {limit} reached.")
        self.limit = limit


@dataclass(frozen=True)
class CreditOwner:
    """Exactly one of user_id (signed in) or guest_key (hashed device id, or IP
    when the browser sent none). A guest's cap_key names the daily allowance
    shared by every guest on the same IP, so new device ids cannot mint
    unlimited free credits."""
    user_id: uuid.UUID | None = None
    guest_key: str | None = None
    cap_key: str | None = None

    def __post_init__(self) -> None:
        if (self.user_id is None) == (self.guest_key is None):
            raise ValueError("A credit owner needs exactly one of user_id or guest_key.")
        if self.cap_key is not None and self.user_id is not None:
            raise ValueError("Only guests share an IP allowance.")

    @property
    def is_guest(self) -> bool:
        return self.user_id is None


@dataclass(frozen=True)
class CreditSummary:
    free_left: int
    free_daily: int
    purchased_balance: int
    questions_left: int
    is_paid: bool

    @property
    def available(self) -> int:
        return self.free_left + self.purchased_balance


def ist_today(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(IST).date()


def video_credit_cost(duration_seconds: int) -> int:
    """Every started minute costs one credit; a non-empty video costs at least one."""
    if duration_seconds <= 0:
        raise ValueError("Video duration must be positive.")
    return math.ceil(duration_seconds / 60)


def video_reservation_key(video_id: uuid.UUID, run: int = 0) -> str:
    return f"video:{video_id}:{run}"


def owner_for_video(video) -> CreditOwner | None:
    """None only for guest videos submitted before credits existed."""
    if video.user_id is not None:
        return CreditOwner(user_id=video.user_id)
    guest_key = getattr(video, "guest_key", None)
    if not guest_key:
        return None
    return CreditOwner(guest_key=guest_key, cap_key=getattr(video, "guest_cap_key", None))


def short_reservation_key(short_id: uuid.UUID, attempt_id: uuid.UUID) -> str:
    # A retried Short reuses its row with a new attempt, so each attempt holds separately.
    return f"short:{short_id}:{attempt_id}"


def audio_merge_credit_cost(segment_seconds: list[int]) -> int:
    """Started minutes of all selected audio, plus a fixed fee per track after the first."""
    if not segment_seconds or min(segment_seconds) <= 0:
        raise ValueError("Every audio segment must have a positive length.")
    return (math.ceil(sum(segment_seconds) / 60)
            + (len(segment_seconds) - 1) * settings.audio_merge_extra_track_credits)


def audio_merge_reservation_key(merge_id: uuid.UUID, attempt_id: uuid.UUID) -> str:
    return f"audio_merge:{merge_id}:{attempt_id}"


def owner_for_merge(merge) -> CreditOwner:
    if merge.user_id is not None:
        return CreditOwner(user_id=merge.user_id)
    return CreditOwner(guest_key=merge.guest_key, cap_key=merge.guest_cap_key)


def daily_free_credits(owner: CreditOwner) -> int:
    return settings.guest_daily_credits if owner.is_guest else settings.user_daily_credits


def daily_question_limit(owner: CreditOwner, purchased_balance: int) -> int:
    if owner.is_guest:
        return settings.guest_daily_questions
    if purchased_balance > 0:
        return settings.paid_daily_questions
    return settings.user_daily_questions


def split_charge(free_left: int, purchased_balance: int, amount: int) -> tuple[int, int]:
    """Returns (from_free, from_purchased); free credits are always spent first."""
    if amount <= 0:
        raise ValueError("Charge must be positive.")
    if free_left + purchased_balance < amount:
        raise InsufficientCreditsError(amount, free_left + purchased_balance)
    from_free = min(free_left, amount)
    return from_free, amount - from_free


def refund_on_failure(reason: str | None) -> bool:
    return reason not in USER_FAULT_REASONS


def roll_daily(account: CreditAccount, today: date) -> None:
    if account.daily_date != today:
        account.daily_date = today
        account.daily_free_used = 0
        account.daily_chat_used = 0


class CreditService:
    def __init__(self, db: AsyncSession, *, commit: bool = True):
        """commit=False only flushes, so the caller's own commit makes the
        credit change and its work atomic (and a rollback undoes both)."""
        self.db = db
        self._commit = commit

    async def _done(self) -> None:
        if self._commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def _lock(self, *, user_id: uuid.UUID | None = None, guest_key: str | None = None) -> CreditAccount:
        """Gets or creates an account and locks it for this transaction."""
        today = ist_today()
        await self.db.execute(insert(CreditAccount).values(
            id=uuid.uuid4(), user_id=user_id, guest_key=guest_key, daily_date=today,
        ).on_conflict_do_nothing())
        column = CreditAccount.user_id if user_id else CreditAccount.guest_key
        account = (await self.db.execute(
            select(CreditAccount).where(column == (user_id or guest_key))
            .with_for_update().execution_options(populate_existing=True)
        )).scalar_one()
        roll_daily(account, today)
        return account

    async def _account(self, owner: CreditOwner) -> CreditAccount:
        return await self._lock(user_id=owner.user_id, guest_key=owner.guest_key)

    async def _accounts(self, owner: CreditOwner) -> tuple[CreditAccount, CreditAccount | None]:
        """The wallet and, for guests, their IP's shared allowance. Always locked
        wallet first so concurrent guests on one IP cannot deadlock."""
        wallet = await self._account(owner)
        cap = await self._lock(guest_key=owner.cap_key) if owner.cap_key else None
        return wallet, cap

    def _summary(self, owner: CreditOwner, account: CreditAccount,
                 cap: CreditAccount | None = None) -> CreditSummary:
        free_daily = daily_free_credits(owner)
        free_left = free_daily - account.daily_free_used
        questions_left = daily_question_limit(owner, account.purchased_balance) - account.daily_chat_used
        if cap is not None:
            free_left = min(free_left, settings.guest_ip_daily_credits - cap.daily_free_used)
            questions_left = min(questions_left, settings.guest_ip_daily_questions - cap.daily_chat_used)
        return CreditSummary(
            free_left=max(free_left, 0),
            free_daily=free_daily,
            purchased_balance=account.purchased_balance,
            questions_left=max(questions_left, 0),
            is_paid=account.purchased_balance > 0,
        )

    def _ledger(self, account: CreditAccount, *, kind: str, bucket: str, amount: int,
                reservation_id: uuid.UUID | None = None, payment_id: uuid.UUID | None = None,
                note: str | None = None) -> None:
        self.db.add(CreditLedgerEntry(
            account_id=account.id, kind=kind, bucket=bucket, amount=amount,
            reservation_id=reservation_id, payment_id=payment_id,
            purchased_balance_after=account.purchased_balance, note=note,
        ))

    async def summary(self, owner: CreditOwner) -> CreditSummary:
        result = self._summary(owner, *await self._accounts(owner))
        await self._done()
        return result

    async def ensure_available(self, owner: CreditOwner, amount: int = 1) -> CreditSummary:
        """Cheap pre-check before queueing work whose final cost is not known yet."""
        result = await self.summary(owner)
        if result.available < amount:
            raise InsufficientCreditsError(amount, result.available)
        return result

    async def reserve(self, owner: CreditOwner, *, source_type: str, source_id: uuid.UUID,
                      idempotency_key: str, amount: int) -> CreditReservation:
        """Holds credits for one unit of work. Repeating a key returns the
        original reservation without charging again."""
        account, cap = await self._accounts(owner)
        existing = (await self.db.execute(select(CreditReservation).where(
            CreditReservation.idempotency_key == idempotency_key))).scalar_one_or_none()
        if existing is not None:
            await self._done()
            if existing.status == "released":
                raise ReservationClosedError(idempotency_key)
            return existing

        summary = self._summary(owner, account, cap)
        from_free, from_purchased = split_charge(summary.free_left, account.purchased_balance, amount)
        account.daily_free_used += from_free
        account.purchased_balance -= from_purchased
        if cap is not None:
            cap.daily_free_used += from_free
        reservation = CreditReservation(
            id=uuid.uuid4(), account_id=account.id, source_type=source_type, source_id=source_id,
            idempotency_key=idempotency_key, free_amount=from_free,
            purchased_amount=from_purchased, status="held",
            cap_account_id=cap.id if cap is not None else None,
        )
        self.db.add(reservation)
        await self.db.flush()
        if from_free:
            self._ledger(account, kind="reserve", bucket="free", amount=-from_free,
                         reservation_id=reservation.id)
        if from_purchased:
            self._ledger(account, kind="reserve", bucket="purchased", amount=-from_purchased,
                         reservation_id=reservation.id)
        await self._done()
        return reservation

    async def _video_reservations(self, video_id: uuid.UUID) -> list[CreditReservation]:
        return list((await self.db.execute(select(CreditReservation).where(
            CreditReservation.source_type == "video", CreditReservation.source_id == video_id,
        ))).scalars())

    async def video_hold(self, video_id: uuid.UUID) -> CreditReservation | None:
        """The video's current (not refunded) reservation, e.g. when a run
        resumes after waiting for STT quota."""
        return next((r for r in await self._video_reservations(video_id) if r.status != "released"), None)

    async def reserve_video(self, owner: CreditOwner, video_id: uuid.UUID, amount: int) -> CreditReservation:
        """Reserves for a video analysis run. A redelivered task reuses the open
        hold; a run after a refunded failure (task retry) is charged again."""
        await self._account(owner)  # serializes runs of this owner's videos
        previous = await self._video_reservations(video_id)
        active = next((r for r in previous if r.status != "released"), None)
        if active is not None:
            await self._done()
            return active
        return await self.reserve(owner, source_type="video", source_id=video_id,
                                  idempotency_key=video_reservation_key(video_id, len(previous)),
                                  amount=amount)

    async def reservation_id(self, idempotency_key: str) -> uuid.UUID | None:
        return (await self.db.execute(select(CreditReservation.id).where(
            CreditReservation.idempotency_key == idempotency_key))).scalar_one_or_none()

    async def _held(self, reservation_id: uuid.UUID) -> tuple[CreditReservation, CreditAccount] | None:
        reservation = (await self.db.execute(
            select(CreditReservation).where(CreditReservation.id == reservation_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if reservation is None or reservation.status != "held":
            return None
        account = (await self.db.execute(
            select(CreditAccount).where(CreditAccount.id == reservation.account_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalar_one()
        return reservation, account

    async def settle(self, reservation_id: uuid.UUID) -> bool:
        """Makes a hold final. Returns False when it was already settled or released."""
        held = await self._held(reservation_id)
        if held is None:
            await self._done()
            return False
        held[0].status = "settled"
        await self._done()
        return True

    async def finish_failed(self, reservation_id: uuid.UUID, *, reason: str | None) -> bool:
        """Refunds a failed job unless the failure was caused by the content
        itself. Returns True when credits were returned."""
        held = await self._held(reservation_id)
        if held is None:
            await self._done()
            return False
        reservation, account = held
        if not refund_on_failure(reason):
            reservation.status = "settled"
            await self._done()
            return False

        note = f"failure:{reason or 'unknown'}"
        reservation.status = "released"
        roll_daily(account, ist_today())
        # Free credits only return to the allowance of the day they came from;
        # yesterday's allowance has already expired.
        if reservation.free_amount and ist_today(reservation.created_at) == account.daily_date:
            account.daily_free_used = max(account.daily_free_used - reservation.free_amount, 0)
            self._ledger(account, kind="release", bucket="free", amount=reservation.free_amount,
                         reservation_id=reservation.id, note=note)
            if reservation.cap_account_id is not None:
                cap = (await self.db.execute(
                    select(CreditAccount).where(CreditAccount.id == reservation.cap_account_id)
                    .with_for_update().execution_options(populate_existing=True)
                )).scalar_one()
                roll_daily(cap, account.daily_date)
                cap.daily_free_used = max(cap.daily_free_used - reservation.free_amount, 0)
        if reservation.purchased_amount:
            account.purchased_balance += reservation.purchased_amount
            self._ledger(account, kind="release", bucket="purchased",
                         amount=reservation.purchased_amount, reservation_id=reservation.id, note=note)
        await self._done()
        return True

    async def grant_purchase(self, payment: Payment) -> None:
        """Adds a paid pack's credits. The ledger's one-purchase-per-payment
        index makes a second grant fail instead of crediting twice."""
        account = await self._lock(user_id=payment.user_id)
        account.purchased_balance += payment.credits
        self._ledger(account, kind="purchase", bucket="purchased", amount=payment.credits,
                     payment_id=payment.id, note=f"pack:{payment.pack_code}")
        await self._done()

    async def revoke_purchase(self, payment: Payment, *, note: str) -> int:
        """Takes back a refunded or disputed pack's credits, as many as are
        still unspent. Returns the number taken back."""
        account = await self._lock(user_id=payment.user_id)
        taken = min(account.purchased_balance, payment.credits)
        if taken:
            account.purchased_balance -= taken
            self._ledger(account, kind="refund", bucket="purchased", amount=-taken,
                         payment_id=payment.id, note=note)
        await self._done()
        return taken

    async def adjust(self, user_id: uuid.UUID, amount: int, *, note: str) -> int:
        """Manual grant (positive) or deduction (negative) on the purchased
        balance. Returns the new balance; never lets it go below zero."""
        account = await self._lock(user_id=user_id)
        if account.purchased_balance + amount < 0:
            await self.db.rollback()
            raise InsufficientCreditsError(-amount, account.purchased_balance)
        account.purchased_balance += amount
        self._ledger(account, kind="adjust", bucket="purchased", amount=amount, note=note[:250])
        balance = account.purchased_balance
        await self._done()
        return balance

    async def consume_question(self, owner: CreditOwner) -> CreditSummary:
        """Counts one question against today's limit before it is answered."""
        account, cap = await self._accounts(owner)
        if self._summary(owner, account, cap).questions_left <= 0:
            await self._done()
            limit = daily_question_limit(owner, account.purchased_balance)
            if cap is not None:
                limit = min(limit, settings.guest_ip_daily_questions)
            raise ChatLimitError(limit)
        account.daily_chat_used += 1
        if cap is not None:
            cap.daily_chat_used += 1
        result = self._summary(owner, account, cap)
        await self._done()
        return result

    async def return_question(self, owner: CreditOwner) -> None:
        """Gives back a question that failed on our side (e.g. provider outage)."""
        account, cap = await self._accounts(owner)
        for counter in (account, cap):
            if counter is not None:
                counter.daily_chat_used = max(counter.daily_chat_used - 1, 0)
        await self._done()

    async def reconcile_held(self, *, older_than: timedelta) -> int:
        """Finishes holds whose job ended without settling (crash, lost task).

        Decides from the job's real status, never from age alone: a video
        waiting for STT quota can legitimately stay in progress for hours.
        Returns the number of reservations finished.
        """
        cutoff = datetime.now(timezone.utc) - older_than
        rows = (await self.db.execute(select(
            CreditReservation.id, CreditReservation.source_type, CreditReservation.source_id,
            CreditReservation.idempotency_key,
        ).where(CreditReservation.status == "held", CreditReservation.created_at < cutoff))).all()
        finished = 0
        for reservation_id, source_type, source_id, key in rows:
            outcome = await self._job_outcome(source_type, source_id, key)
            if outcome is None:
                continue
            succeeded, reason = outcome
            if succeeded:
                finished += await self.settle(reservation_id)
            else:
                await self.finish_failed(reservation_id, reason=reason)
                finished += 1
        await self._done()
        return finished

    async def _job_outcome(self, source_type: str, source_id: uuid.UUID,
                           key: str) -> tuple[bool, str | None] | None:
        """(succeeded, failure reason) for a finished job, or None while it is still running."""
        now = datetime.now(timezone.utc)
        if source_type == "video":
            video = await self.db.get(Video, source_id)
            if video is None:
                return False, "source_missing"
            if video.status == VideoStatus.COMPLETED:
                return True, None
            if video.status == VideoStatus.FAILED:
                return False, video.processing_stage
            # Same rule as VideoService.get_for_user: a worker that stopped
            # reporting progress is dead, unless it is waiting for STT quota.
            if (video.processing_stage != "waiting_for_quota" and video.processing_updated_at
                    < now - timedelta(seconds=settings.stale_processing_seconds)):
                return False, "stale_processing"
            return None
        if source_type == "audio_merge":
            merge = await self.db.get(AudioMerge, source_id)
            if merge is None:
                return False, "source_missing"
            if key != audio_merge_reservation_key(merge.id, merge.attempt_id):
                return False, "attempt_superseded"
            if merge.status == "completed":
                return True, None
            if merge.status in {"failed", "expired"}:
                return False, merge.error_code or merge.status
            if merge.updated_at < now - timedelta(seconds=settings.audio_merge_timeout_seconds + 1800):
                return False, "JOB_TIMED_OUT"
            return None
        short = await self.db.get(Short, source_id)
        if short is None:
            return False, "source_missing"
        if key != short_reservation_key(short.id, short.attempt_id):
            # A newer attempt replaced this one, so this attempt can never finish.
            return False, "attempt_superseded"
        if short.status == "completed":
            return True, None
        if short.status in {"failed", "expired"}:
            return False, short.error_code or short.status
        # Same timeout ShortService._expire_stalled applies to queued/rendering jobs.
        if short.updated_at < now - timedelta(seconds=settings.shorts_timeout_seconds + 1800):
            return False, "JOB_TIMED_OUT"
        return None
