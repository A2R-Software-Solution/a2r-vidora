"""Shared SlowAPI instance; limits are applied explicitly in route modules."""
import uuid
from ipaddress import ip_address

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.deps import get_current_user_id


def client_key(request: Request) -> str:
    user_id = getattr(request.state, "rate_limit_user_id", None)
    if user_id is not None:
        return f"user:{user_id}"
    host = request.client.host if request.client else "unknown"
    # Trust only the configured proxy suffix, never the arbitrary first entry.
    hops = settings.rate_limit_trusted_proxy_hops
    forwarded = request.headers.get("x-forwarded-for", "").split(",")
    if hops and len(forwarded) >= hops:
        try:
            host = str(ip_address(forwarded[-hops].strip()))
        except ValueError:
            pass
    return f"ip:{host}"


async def rate_limit_user(
    request: Request,
    user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> uuid.UUID | None:
    request.state.rate_limit_user_id = user_id
    return user_id


limiter = Limiter(
    key_func=client_key,
    storage_uri="memory://",
    strategy="fixed-window",
    headers_enabled=True,
    retry_after="delta-seconds",
    key_style="endpoint",
)


def rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    response = _rate_limit_exceeded_handler(request, exc)
    return JSONResponse(
        {"detail": "Too many requests. Please try again later."},
        status_code=429,
        headers={key: value for key, value in response.headers.items()
                 if key.lower() not in {"content-length", "content-type"}},
    )
