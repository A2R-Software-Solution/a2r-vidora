"""Cross-instance STT reservations against the Groq organization budget."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import math

from sqlalchemy import text

from app.core.config import settings
from app.db.session import AsyncSessionLocal


# One conservative budget for all configured Groq STT credentials. This also
# covers the common case in which keys belong to the same organization.
_WINDOWS = ((60, settings.stt_requests_per_minute, None),
            (3600, None, settings.stt_audio_seconds_per_hour),
            (86400, settings.stt_requests_per_day, settings.stt_audio_seconds_per_day))


def _wait_for_capacity(rows: list[tuple[datetime, int]], now: datetime,
                       audio_seconds: int) -> float:
    wait = 0.0
    for window, request_limit, seconds_limit in _WINDOWS:
        recent = [(at, seconds) for at, seconds in rows
                  if at > now - timedelta(seconds=window)]
        if request_limit is not None and len(recent) >= request_limit:
            wait = max(wait, (recent[len(recent) - request_limit][0]
                              + timedelta(seconds=window) - now).total_seconds())
        if seconds_limit is not None:
            used = sum(seconds for _, seconds in recent)
            if used + audio_seconds > seconds_limit:
                for at, seconds in recent:
                    used -= seconds
                    if used + audio_seconds <= seconds_limit:
                        wait = max(wait, (at + timedelta(seconds=window) - now).total_seconds())
                        break
    return wait


class SttQuotaDeferred(Exception):
    """The job should resume in a later Cloud Task instead of holding a worker."""

    def __init__(self, delay_seconds: float) -> None:
        super().__init__("STT quota is temporarily exhausted")
        self.delay_seconds = delay_seconds


async def reserve_stt_request(audio_seconds: float) -> None:
    """Wait for capacity, then reserve atomically before sending a request."""
    if not 0 < audio_seconds <= settings.stt_audio_seconds_per_hour:
        raise ValueError("Invalid STT request duration")
    audio_seconds = math.ceil(audio_seconds)
    while True:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # Transaction-scoped lock makes the read/check/insert atomic
                # across Cloud Function instances sharing PostgreSQL.
                await session.execute(text("SELECT pg_advisory_xact_lock(8519035)"))
                now = datetime.now(timezone.utc)
                await session.execute(text(
                    "DELETE FROM stt_quota_reservations WHERE reserved_at <= :oldest"
                ), {"oldest": now - timedelta(days=1)})
                rows = (await session.execute(text(
                    "SELECT reserved_at, audio_seconds FROM stt_quota_reservations "
                    "WHERE reserved_at > :oldest ORDER BY reserved_at"
                ), {"oldest": now - timedelta(days=1)})).all()
                wait = _wait_for_capacity(rows, now, audio_seconds)
                if wait <= 0:
                    await session.execute(text(
                        "INSERT INTO stt_quota_reservations (reserved_at, audio_seconds) "
                        "VALUES (:at, :seconds)"
                    ), {"at": now, "seconds": math.ceil(audio_seconds)})
                    return
        if wait > 10:
            raise SttQuotaDeferred(wait + 2)
        await asyncio.sleep(max(wait, 0.1) + 0.1)
