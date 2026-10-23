import json

from fastapi import Depends, HTTPException, Request, Response
from app.core.config import settings
from app.core.rate_limit import limiter, rate_limit_user
from app.deps import get_db
from app.integration import razorpay_client
from app.integration.razorpay_client import RazorpayError
from app.middleware.logging import logger
from app.schemas.billing_schema import (OrderRequest, OrderResponse, PackResponse,
                                        VerifyRequest, VerifyResponse)
from app.services.payment_service import (PACKS, InvalidPaymentSignatureError, PaymentNotFoundError,
                                          PaymentService)
from app.utils.router_config import create_router

router = create_router(prefix="/billing", tags=["Billing"])


def _require_payments():
    if not settings.payments_enabled:
        raise HTTPException(503, "Payments are not available yet.")


def _require_user(user_id):
    if user_id is None:
        raise HTTPException(401, "Sign in to buy credits.")
    return user_id


@router.get("/packs", response_model=list[PackResponse])
@limiter.limit("50/minute")
async def list_packs(request: Request, response: Response):
    return [PackResponse(code=p.code, credits=p.credits, amount_cents=p.amount_cents, currency=p.currency)
            for p in PACKS.values()]


@router.post("/orders", response_model=OrderResponse, status_code=201)
@limiter.limit("10/minute")
async def create_order(payload: OrderRequest, request: Request, response: Response,
                       db=Depends(get_db), user_id=Depends(rate_limit_user)):
    _require_payments()
    try:
        payment = await PaymentService(db).create_order(_require_user(user_id), payload.pack_code)
    except RazorpayError as exc:
        logger.error("razorpay_order_failed error=%s", exc)
        raise HTTPException(503, "Payment provider is temporarily unavailable.") from exc
    return OrderResponse(payment_id=payment.id, order_id=payment.provider_order_id,
                         key_id=settings.razorpay_key_id, amount_cents=payment.amount_cents,
                         currency=payment.currency, credits=payment.credits)


@router.post("/verify", response_model=VerifyResponse)
@limiter.limit("20/minute")
async def verify_payment(payload: VerifyRequest, request: Request, response: Response,
                         db=Depends(get_db), user_id=Depends(rate_limit_user)):
    _require_payments()
    try:
        payment = await PaymentService(db).verify_checkout(
            _require_user(user_id), order_id=payload.razorpay_order_id,
            payment_id=payload.razorpay_payment_id, signature=payload.razorpay_signature)
    except InvalidPaymentSignatureError as exc:
        raise HTTPException(400, "Payment could not be verified.") from exc
    except PaymentNotFoundError as exc:
        raise HTTPException(404, "Payment not found.") from exc
    except RazorpayError as exc:
        logger.error("razorpay_verify_failed error=%s", exc)
        raise HTTPException(503, "Payment provider is temporarily unavailable.") from exc
    return VerifyResponse(payment_id=payment.id, status=payment.status, credits=payment.credits)


@router.post("/webhook")
@limiter.limit("300/minute")
async def razorpay_webhook(request: Request, response: Response, db=Depends(get_db)):
    """Razorpay retries on any non-2xx, so a crash here is retried safely."""
    raw = await request.body()
    if not razorpay_client.webhook_signature_valid(raw, request.headers.get("x-razorpay-signature")):
        raise HTTPException(400, "Invalid signature.")
    await PaymentService(db).handle_webhook(json.loads(raw))
    return {"status": "ok"}
