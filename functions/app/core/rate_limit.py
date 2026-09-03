"""
ye in-memory hai, isliye Firebase Cloud Functions pe multiple instances chalne par har instance ka apna alag counter hoga — global rate limit nahi hoga. Ye checkpoint ke README note ("handled at Firebase/middleware level, not DB") ke mutabik hi hai, lekin production-scale abuse-proofing ke liye eventually isko Redis ya Firebase-level rate limiting se replace karna better hoga. MVP ke liye ye theek hai.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status

from app.deps import get_current_user_id

_VIDEO_SUBMIT_LIMIT = 5
_VIDEO_SUBMIT_WINDOW_SECONDS = 600

_QUESTION_LIMIT = 10
_QUESTION_WINDOW_SECONDS = 600

_buckets: dict[str, deque[float]] = defaultdict(deque)


def _client_identity(request: Request, user_id: uuid.UUID | None) -> str:
    if user_id is not None:
        return f"user:{user_id}"
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def _check_and_record(key: str, *, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
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
    _check_and_record(
        f"question:{identity}:{video_id}",
        limit=_QUESTION_LIMIT,
        window_seconds=_QUESTION_WINDOW_SECONDS,
    )