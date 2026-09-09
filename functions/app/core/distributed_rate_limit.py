"""Postgres atomic fixed-window admission, independent of instance count.

This limits admitted expensive work, not incoming billed HTTP invocations.
Missing database/migration fails closed. Limits use the database clock.
"""
import asyncio
import hashlib

from fastapi import HTTPException
from sqlalchemy import BigInteger, cast, func
from sqlalchemy.dialects.postgresql import insert

from app.db.session import AsyncSessionLocal
from app.models.rate_limit_model import RateLimitBucket


def admission_statement(key: str, limit: int, window_seconds: int):
    bucket = cast(func.floor(func.extract("epoch", func.now()) / window_seconds), BigInteger) * window_seconds
    return insert(RateLimitBucket).values(
        scope_key=hashlib.sha256(key.encode()).hexdigest(),
        window_start=bucket,
        requests=1,
    ).on_conflict_do_update(
        index_elements=[RateLimitBucket.scope_key, RateLimitBucket.window_start],
        set_={"requests": RateLimitBucket.requests + 1},
        where=RateLimitBucket.requests < limit,
    ).returning(RateLimitBucket.requests)


async def admit(key: str, *, limit: int, window_seconds: int) -> None:
    try:
        async with asyncio.timeout(5):
            async with AsyncSessionLocal() as db:
                result = await db.execute(admission_statement(key, limit, window_seconds))
                allowed = result.scalar_one_or_none() is not None
                await db.commit()
    except Exception:
        raise HTTPException(status_code=503, detail="Request admission unavailable. Try later.") from None
    if not allowed:
        raise HTTPException(
            status_code=429, detail="Too many requests. Please try later.",
            headers={"Retry-After": str(window_seconds)},
        )
