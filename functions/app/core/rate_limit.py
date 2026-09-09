"""
Production uses atomic shared PostgreSQL budgets; development uses bounded
in-memory counters. This limits expensive work, not billed HTTP invocations.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException, Request, status

from app.deps import get_current_user_id
from app.core.config import settings
from app.core.distributed_rate_limit import admit

_VIDEO_SUBMIT_LIMIT = 5
_VIDEO_SUBMIT_WINDOW_SECONDS = 600

_QUESTION_LIMIT = 10
_QUESTION_WINDOW_SECONDS = 600

_buckets: dict[str, deque[float]] = defaultdict(deque)
_bucket_lock = Lock()


def _client_identity(request: Request, user_id: uuid.UUID | None) -> str:
    if user_id is not None:
        return f"user:{user_id}"
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def _check_and_record(key: str, *, limit: int, window_seconds: int) -> None:
    with _bucket_lock:
        _check_locked(key, limit=limit, window_seconds=window_seconds)


def _check_locked(key: str, *, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    # Bound memory under high-cardinality client traffic. Never evict active
    # entries to admit a new client (that would bypass the limiter).
    if key not in _buckets and len(_buckets) >= 10000:
        for stale in [k for k, v in _buckets.items() if not v or now - v[-1] > 600]:
            del _buckets[stale]
        if len(_buckets) >= 10000:
            raise HTTPException(status_code=503, detail="Service busy. Please try later.")
    bucket = _buckets[key]

    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()

    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

    bucket.append(now)


async def enforce_submit_rate_limit(
    request: Request,
    user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    identity = _client_identity(request, user_id)
    if settings.is_production:
        await admit(f"submit:{identity}", limit=_VIDEO_SUBMIT_LIMIT, window_seconds=_VIDEO_SUBMIT_WINDOW_SECONDS)
        return
    _check_and_record(
        f"submit:{identity}",
        limit=_VIDEO_SUBMIT_LIMIT,
        window_seconds=_VIDEO_SUBMIT_WINDOW_SECONDS,
    )


async def enforce_question_rate_limit(
    request: Request,
    video_id: uuid.UUID,
    user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> None:
    identity = _client_identity(request, user_id)
    if settings.is_production:
        # Account/IP total, not per-video: switching IDs must not reset the budget.
        await admit(f"question:{identity}", limit=_QUESTION_LIMIT, window_seconds=_QUESTION_WINDOW_SECONDS)
        return
    _check_and_record(
        f"question:{identity}:{video_id}",
        limit=_QUESTION_LIMIT,
        window_seconds=_QUESTION_WINDOW_SECONDS,
    )
