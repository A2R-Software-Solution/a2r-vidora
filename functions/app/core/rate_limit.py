"""Shared SlowAPI instance; limits are applied explicitly in route modules."""
import hashlib
import uuid
from ipaddress import ip_address

from fastapi import Depends, Request
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


def _hashed(kind: str, value: str) -> str:
    return hashlib.sha256(f"{kind}:{value}".encode()).hexdigest()


def guest_device_id(request: Request) -> str | None:
    """The browser's random X-Guest-Id, if it is a well-formed UUID."""
    headers = request.headers if "headers" in request.scope else {}
    try:
        return str(uuid.UUID(headers.get("x-guest-id", "")))
    except ValueError:
        return None


def credit_owner_for(request: Request, user_id: uuid.UUID | None) -> CreditOwner:
    """Signed-in users own their wallet. A guest gets one wallet per browser
    (X-Guest-Id), or per IP when the header is missing, and every guest also
    draws on a daily allowance shared by their IP. Identifiers are stored
    only as hashes."""
    if user_id is not None:
        return CreditOwner(user_id=user_id)
    ip = client_ip(request)
    device = guest_device_id(request)
    wallet = _hashed("guest-device", device) if device else _hashed("guest-ip", ip)
    return CreditOwner(guest_key=wallet, cap_key=_hashed("guest-ip-cap", ip))


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
