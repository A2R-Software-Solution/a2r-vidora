"""Shared SlowAPI instance; limits are applied explicitly in route modules."""
import uuid
from ipaddress import ip_address

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.deps import get_current_user_id
from app.services.credit_service import CreditOwner


def client_ip(request: Request) -> str:
    client = request.scope.get("client")
    host = client[0] if client else "unknown"
    # Trust only the configured proxy suffix, never the arbitrary first entry.
    hops = settings.rate_limit_trusted_proxy_hops
    headers = request.headers if "headers" in request.scope else {}
    forwarded = headers.get("x-forwarded-for", "").split(",")
    if hops and len(forwarded) >= hops:
        try:
            host = str(ip_address(forwarded[-hops].strip()))
        except ValueError:
            pass
    return host


def client_key(request: Request) -> str:
    user_id = getattr(request.state, "rate_limit_user_id", None)
    if user_id is not None:
        return f"user:{user_id}"
    return f"ip:{client_ip(request)}"


SIGN_IN_REQUIRED = "Please sign in to use Vidora."


def credit_owner_for(request: Request, user_id: uuid.UUID | None) -> CreditOwner:
    """The signed-in user's wallet. Every feature that goes through a wallet
    (analysis, questions, Shorts, Song Merger, downloads) needs an account,
    so a guest is refused here with 401."""
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIGN_IN_REQUIRED)
    return CreditOwner(user_id=user_id)


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
