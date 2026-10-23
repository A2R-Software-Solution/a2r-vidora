"""Minimal Razorpay REST client: orders, payment lookup and signature checks."""
from __future__ import annotations

import hashlib
import hmac

import httpx

from app.core.config import settings


class RazorpayError(Exception):
    """Razorpay is unreachable, misconfigured or rejected the request."""


def _credentials() -> tuple[str, str]:
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        raise RazorpayError("Razorpay credentials are not configured.")
    return settings.razorpay_key_id, settings.razorpay_key_secret


async def _request(method: str, path: str, **kwargs) -> dict:
    try:
        async with httpx.AsyncClient(base_url=settings.razorpay_api_url, auth=_credentials(),
                                     timeout=settings.razorpay_timeout_seconds) as client:
            response = await client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise RazorpayError(f"Razorpay request failed: {type(exc).__name__}") from exc
    if response.status_code >= 400:
        # Keep only Razorpay's error code for logs, never the request.
        try:
            code = response.json().get("error", {}).get("code")
        except ValueError:
            code = None
        raise RazorpayError(f"Razorpay returned {response.status_code} ({code})")
    return response.json()


async def create_order(*, amount: int, currency: str, receipt: str, notes: dict[str, str]) -> dict:
    """amount is in the currency's smallest unit (cents for USD)."""
    return await _request("POST", "/orders", json={
        "amount": amount, "currency": currency, "receipt": receipt, "notes": notes,
    })


async def fetch_payment(payment_id: str) -> dict:
    return await _request("GET", f"/payments/{payment_id}")


def _matches(secret: str | None, message: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def checkout_signature_valid(order_id: str, payment_id: str, signature: str | None) -> bool:
    """Checkout returns HMAC-SHA256("order_id|payment_id") keyed with the API secret."""
    return _matches(settings.razorpay_key_secret, f"{order_id}|{payment_id}".encode(), signature)


def webhook_signature_valid(raw_body: bytes, signature: str | None) -> bool:
    """Webhooks sign the raw body with the separate webhook secret."""
    return _matches(settings.razorpay_webhook_secret, raw_body, signature)
