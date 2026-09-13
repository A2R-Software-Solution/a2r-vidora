"""Server-side verification for reCAPTCHA v3 action tokens."""

from __future__ import annotations

import asyncio
import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import logger

_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
_TIMEOUT_SECONDS = 5


def _verify_token(token: str) -> dict:
    body = urlencode({"secret": settings.recaptcha_secret_key, "response": token}).encode()
    request = Request(_VERIFY_URL, data=body, method="POST")
    with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # nosec B310: fixed Google endpoint
        return json.loads(response.read().decode("utf-8"))


async def verify_recaptcha(token: str | None, *, expected_action: str) -> None:
    """Reject invalid, replayed, wrong-action, or low-score bot requests."""
    if not settings.recaptcha_secret_key:
        if settings.is_production:
            logger.error("reCAPTCHA secret is missing in production")
            raise HTTPException(status_code=503, detail="Bot protection is temporarily unavailable.")
        return

    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bot verification is required.")

    try:
        result = await asyncio.to_thread(_verify_token, token)
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("reCAPTCHA verification request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Bot verification is temporarily unavailable.") from None

    valid = result.get("success") is True
    action_matches = result.get("action") == expected_action
    score = result.get("score")
    score_passes = isinstance(score, (int, float)) and score >= settings.recaptcha_min_score
    allowed_hosts = settings.recaptcha_allowed_hostnames
    hostname = result.get("hostname")
    hostname_matches = not allowed_hosts or (
        isinstance(hostname, str) and hostname.lower() in allowed_hosts
    )

    if not (valid and action_matches and score_passes and hostname_matches):
        logger.info(
            "reCAPTCHA rejected request success=%s action_matches=%s score=%s hostname_matches=%s",
            valid, action_matches, score, hostname_matches,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request could not be verified.")
