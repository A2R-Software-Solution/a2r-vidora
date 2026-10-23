"""Razorpay credit packs. Razorpay itself is always mocked; database tests need
a disposable PostgreSQL at TEST_DATABASE_URL (see test_credits.py)."""
import hashlib
import hmac
import json
import os
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

from app.core.config import settings
from app.integration import razorpay_client
from app.services.payment_service import PACKS


def sign(secret, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


class SignatureTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("razorpay_key_secret", "key-secret"), ("razorpay_webhook_secret", "hook-secret")):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_checkout_signature_uses_order_and_payment_ids_and_api_secret(self):
        good = sign("key-secret", b"order_1|pay_1")
        self.assertTrue(razorpay_client.checkout_signature_valid("order_1", "pay_1", good))
        self.assertFalse(razorpay_client.checkout_signature_valid("order_1", "pay_2", good))
        self.assertFalse(razorpay_client.checkout_signature_valid("order_1", "pay_1", sign("hook-secret", b"order_1|pay_1")))
        self.assertFalse(razorpay_client.checkout_signature_valid("order_1", "pay_1", None))

    def test_webhook_signature_uses_raw_body_and_webhook_secret(self):
        body = b'{"event": "order.paid"}'
        self.assertTrue(razorpay_client.webhook_signature_valid(body, sign("hook-secret", body)))
        self.assertFalse(razorpay_client.webhook_signature_valid(body + b" ", sign("hook-secret", body)))
        self.assertFalse(razorpay_client.webhook_signature_valid(body, sign("key-secret", body)))

    def test_missing_secret_never_validates(self):
        with patch.object(settings, "razorpay_webhook_secret", None):
            self.assertFalse(razorpay_client.webhook_signature_valid(b"{}", sign("", b"{}")))

    def test_packs_match_agreed_prices(self):
        self.assertEqual({code: (p.amount_cents, p.credits, p.currency) for code, p in PACKS.items()},
                         {"topup": (259, 120, "USD"), "starter": (500, 300, "USD"), "pro": (1000, 800, "USD")})


class BillingApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app.core.rate_limit import limiter
        from app.deps import get_current_user_id, get_db
        from app.main import app
        from app.routes import billing_routes
        limiter.reset()
        self.addCleanup(limiter.reset)
        self.user = None

        async def user():
            return self.user

        async def db():
            yield Mock()
        app.dependency_overrides[get_current_user_id] = user
        app.dependency_overrides[get_db] = db
        self.addCleanup(app.dependency_overrides.clear)
        self.payments = Mock(handle_webhook=AsyncMock(), create_order=AsyncMock())
        for target, name, value in ((billing_routes, "PaymentService", Mock(return_value=self.payments)),
                                    (settings, "payments_enabled", True),
                                    (settings, "razorpay_webhook_secret", "hook-secret")):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_packs_are_public(self):
        self.assertEqual(len(self.client.get("/billing/packs").json()), 3)

    def test_guests_must_sign_in_to_buy(self):
        response = self.client.post("/billing/orders", json={"pack_code": "pro"})
        self.assertEqual(response.status_code, 401)
        self.payments.create_order.assert_not_awaited()

    def test_unknown_pack_is_rejected(self):
        self.user = uuid.uuid4()
        self.assertEqual(self.client.post("/billing/orders", json={"pack_code": "free"}).status_code, 422)

    def test_disabled_payments_refuse_orders(self):
        self.user = uuid.uuid4()
        with patch.object(settings, "payments_enabled", False):
            self.assertEqual(self.client.post("/billing/orders", json={"pack_code": "pro"}).status_code, 503)

    def test_webhook_requires_a_valid_signature(self):
        body = json.dumps({"event": "order.paid", "payload": {}}).encode()
        bad = self.client.post("/billing/webhook", content=body, headers={"X-Razorpay-Signature": "forged"})
        self.assertEqual(bad.status_code, 400)
        self.payments.handle_webhook.assert_not_awaited()
        good = self.client.post("/billing/webhook", content=body,
                                headers={"X-Razorpay-Signature": sign("hook-secret", body)})
        self.assertEqual(good.status_code, 200)
        self.payments.handle_webhook.assert_awaited_once_with(json.loads(body))


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL is not set")
class PaymentDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from app.models.user_model import User
        self.engine = create_async_engine(TEST_DATABASE_URL)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.sessions() as db:
            user = User(firebase_uid=str(uuid.uuid4()), email=f"{uuid.uuid4()}@test.local")
            db.add(user)
            await db.commit()
        self.user_id = user.id
        for name, value in (("razorpay_key_secret", "key-secret"),):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        await self.engine.dispose()

    def service(self, db):
        from app.services.payment_service import PaymentService
        return PaymentService(db)

    async def order(self, pack="starter", user_id=None):
        order_id = f"order_{uuid.uuid4().hex[:14]}"
        with patch.object(razorpay_client, "create_order", AsyncMock(return_value={"id": order_id})):
            async with self.sessions() as db:
                return await self.service(db).create_order(user_id or self.user_id, pack)

    def captured(self, payment, **overrides):
        entity = {"id": f"pay_{uuid.uuid4().hex[:14]}", "order_id": payment.provider_order_id,
                  "status": "captured", "amount": payment.amount_cents, "currency": payment.currency}
        return {**entity, **overrides}

    async def webhook(self, event, key, entity):
        async with self.sessions() as db:
            await self.service(db).handle_webhook({"event": event, "payload": {key: {"entity": entity}}})

    async def balance(self):
        from app.services.credit_service import CreditOwner, CreditService
        async with self.sessions() as db:
            return (await CreditService(db).summary(CreditOwner(user_id=self.user_id))).purchased_balance

    async def status(self, payment):
        from app.models.credit_model import Payment
        async with self.sessions() as db:
            return (await db.get(Payment, payment.id)).status

    async def test_pack_is_credited_once_whichever_confirmation_arrives(self):
        payment = await self.order("starter")
        entity = self.captured(payment)
        await self.webhook("payment.captured", "payment", entity)
        await self.webhook("order.paid", "payment", entity)
        with patch.object(razorpay_client, "fetch_payment", AsyncMock(return_value=entity)):
            async with self.sessions() as db:
                result = await self.service(db).verify_checkout(
                    self.user_id, order_id=payment.provider_order_id, payment_id=entity["id"],
                    signature=sign("key-secret", f"{payment.provider_order_id}|{entity['id']}".encode()))
        self.assertEqual(result.status, "paid")
        self.assertEqual(await self.balance(), 300)

    async def test_verify_credits_immediately_when_captured(self):
        payment = await self.order("topup")
        entity = self.captured(payment)
        with patch.object(razorpay_client, "fetch_payment", AsyncMock(return_value=entity)):
            async with self.sessions() as db:
                await self.service(db).verify_checkout(
                    self.user_id, order_id=payment.provider_order_id, payment_id=entity["id"],
                    signature=sign("key-secret", f"{payment.provider_order_id}|{entity['id']}".encode()))
        self.assertEqual(await self.balance(), 120)

    async def test_authorized_but_uncaptured_payment_waits_for_the_webhook(self):
        payment = await self.order("pro")
        await self.webhook("payment.captured", "payment", self.captured(payment, status="authorized"))
        self.assertEqual((await self.balance(), await self.status(payment)), (0, "created"))
        await self.webhook("payment.captured", "payment", self.captured(payment))
        self.assertEqual(await self.balance(), 800)

    async def test_wrong_amount_or_currency_is_never_credited(self):
        payment = await self.order("pro")
        await self.webhook("payment.captured", "payment", self.captured(payment, amount=259))
        await self.webhook("payment.captured", "payment", self.captured(payment, currency="INR"))
        self.assertEqual((await self.balance(), await self.status(payment)), (0, "created"))

    async def test_forged_or_foreign_verification_is_rejected(self):
        from app.services.payment_service import InvalidPaymentSignatureError, PaymentNotFoundError
        payment = await self.order()
        signature = sign("key-secret", f"{payment.provider_order_id}|pay_x".encode())
        async with self.sessions() as db:
            with self.assertRaises(InvalidPaymentSignatureError):
                await self.service(db).verify_checkout(self.user_id, order_id=payment.provider_order_id,
                                                       payment_id="pay_x", signature="forged")
            with self.assertRaises(PaymentNotFoundError):
                await self.service(db).verify_checkout(uuid.uuid4(), order_id=payment.provider_order_id,
                                                       payment_id="pay_x", signature=signature)
        self.assertEqual(await self.balance(), 0)

    async def test_failed_attempt_then_successful_retry_on_the_same_order(self):
        payment = await self.order("starter")
        await self.webhook("payment.failed", "payment", self.captured(payment, status="failed"))
        self.assertEqual(await self.status(payment), "failed")
        await self.webhook("payment.captured", "payment", self.captured(payment))
        self.assertEqual((await self.balance(), await self.status(payment)), (300, "paid"))

    async def test_refund_takes_back_only_unspent_credits_once(self):
        from app.services.credit_service import CreditOwner, CreditService
        payment = await self.order("starter")
        entity = self.captured(payment)
        await self.webhook("payment.captured", "payment", entity)
        async with self.sessions() as db:
            # Spend the whole free allowance plus 100 purchased credits.
            await CreditService(db).reserve(CreditOwner(user_id=self.user_id), source_type="video",
                                            source_id=uuid.uuid4(), idempotency_key=f"t:{uuid.uuid4()}",
                                            amount=settings.user_daily_credits + 100)
        refund = {"id": "rfnd_1", "payment_id": entity["id"]}
        await self.webhook("refund.processed", "refund", refund)
        await self.webhook("refund.processed", "refund", refund)
        await self.webhook("payment.dispute.created", "dispute", refund)
        self.assertEqual((await self.balance(), await self.status(payment)), (0, "refunded"))

    async def test_dispute_freezes_the_pack(self):
        payment = await self.order("topup")
        entity = self.captured(payment)
        await self.webhook("order.paid", "payment", entity)
        await self.webhook("payment.dispute.created", "dispute", {"id": "disp_1", "payment_id": entity["id"]})
        self.assertEqual((await self.balance(), await self.status(payment)), (0, "disputed"))

    async def test_events_for_other_orders_are_ignored(self):
        await self.webhook("payment.captured", "payment", {"id": "pay_x", "order_id": "order_not_ours",
                                                           "status": "captured", "amount": 500, "currency": "USD"})
        await self.webhook("refund.processed", "refund", {"payment_id": "pay_not_ours"})
        self.assertEqual(await self.balance(), 0)


if __name__ == "__main__":
    unittest.main()
