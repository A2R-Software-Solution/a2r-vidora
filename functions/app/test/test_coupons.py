"""Coupon rules that need no database: pricing and when a coupon may be used."""
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.models.coupon_model import Coupon
from app.services.coupon_service import CouponError, coupon_problem, discounted, normalize_code

NOW = datetime(2026, 11, 24, tzinfo=timezone.utc)


def coupon(**fields) -> Coupon:
    values = dict(code="LAUNCH50", percent_off=50, bonus_credits=0, packs=None, currency=None,
                  max_uses=None, per_user_limit=1, expires_at=None, active=True)
    return Coupon(**(values | fields))


def problem(c, *, currency="INR", pack_code="starter", used_total=0, used_by_user=0):
    return coupon_problem(c, now=NOW, currency=currency, pack_code=pack_code,
                          used_total=used_total, used_by_user=used_by_user)


class CouponPriceTests(unittest.TestCase):
    def test_percent_off_lowers_the_price(self):
        self.assertEqual(discounted(20000, 300, coupon(percent_off=50)).amount, 10000)
        self.assertEqual(discounted(259, 120, coupon(percent_off=10)).amount, 233)

    def test_price_never_drops_below_one_rupee_or_dollar(self):
        self.assertEqual(discounted(10000, 120, coupon(percent_off=100)).amount, 100)
        self.assertEqual(discounted(259, 120, coupon(percent_off=99)).amount, 100)

    def test_bonus_credits_are_added(self):
        price = discounted(20000, 300, coupon(percent_off=0, bonus_credits=50))
        self.assertEqual((price.amount, price.credits), (20000, 350))

    def test_codes_are_case_insensitive(self):
        self.assertEqual(normalize_code("  launch50 "), "LAUNCH50")


class CouponRuleTests(unittest.TestCase):
    def test_a_valid_coupon_has_no_problem(self):
        self.assertIsNone(problem(coupon()))

    def test_unknown_or_inactive_coupons_are_refused(self):
        self.assertEqual(problem(None), "This coupon code is not valid.")
        self.assertEqual(problem(coupon(active=False)), "This coupon code is not valid.")

    def test_expired_coupons_are_refused(self):
        self.assertEqual(problem(coupon(expires_at=NOW - timedelta(seconds=1))), "This coupon has expired.")
        self.assertIsNone(problem(coupon(expires_at=NOW + timedelta(days=1))))

    def test_currency_and_pack_limits(self):
        self.assertIn("USD", problem(coupon(currency="INR"), currency="USD"))
        self.assertIsNone(problem(coupon(currency="INR"), currency="INR"))
        self.assertEqual(problem(coupon(packs="pro"), pack_code="starter"), "This coupon does not apply to this pack.")
        self.assertIsNone(problem(coupon(packs="starter,pro"), pack_code="starter"))
        # Checking a code before a pack is chosen skips the pack rule.
        self.assertIsNone(problem(coupon(packs="pro"), pack_code=None))

    def test_use_limits(self):
        self.assertEqual(problem(coupon(max_uses=10), used_total=10), "This coupon has been used up.")
        self.assertIsNone(problem(coupon(max_uses=10), used_total=9))
        self.assertEqual(problem(coupon(per_user_limit=1), used_by_user=1), "You have already used this coupon.")
        self.assertIsNone(problem(coupon(per_user_limit=None), used_by_user=5))


class CouponApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app.core.rate_limit import limiter
        from app.deps import get_current_user_id, get_db
        from app.main import app
        from app.routes import billing_routes
        limiter.reset()
        self.addCleanup(limiter.reset)
        self.user = uuid.uuid4()

        async def user():
            return self.user

        async def db():
            yield None
        app.dependency_overrides[get_current_user_id] = user
        app.dependency_overrides[get_db] = db
        self.addCleanup(app.dependency_overrides.clear)
        service = patch.object(billing_routes, "CouponService")
        self.coupons = service.start().return_value
        self.addCleanup(service.stop)
        payments = patch.object(billing_routes, "PaymentService")
        self.payments = payments.start().return_value
        self.addCleanup(payments.stop)
        enabled = patch.object(settings, "payments_enabled", True)
        enabled.start()
        self.addCleanup(enabled.stop)
        self.client = TestClient(app)

    def test_check_returns_the_coupon_benefit(self):
        self.coupons.usable = AsyncMock(return_value=coupon(packs="pro", bonus_credits=20))
        body = self.client.post("/billing/coupons/check", json={"code": "launch50", "currency": "INR"}).json()
        self.assertEqual(body, {"code": "LAUNCH50", "percent_off": 50, "bonus_credits": 20, "packs": ["pro"]})

    def test_refused_coupon_explains_why(self):
        self.coupons.usable = AsyncMock(side_effect=CouponError("This coupon has expired."))
        response = self.client.post("/billing/coupons/check", json={"code": "OLD"})
        self.assertEqual((response.status_code, response.json()["detail"]), (400, "This coupon has expired."))

    def test_order_with_a_refused_coupon_is_a_400(self):
        self.payments.create_order = AsyncMock(side_effect=CouponError("This coupon has been used up."))
        response = self.client.post("/billing/orders", json={"pack_code": "pro", "coupon_code": "GONE"})
        self.assertEqual(response.status_code, 400)
        self.payments.create_order.assert_awaited_once_with(self.user, "pro", "USD", "GONE")
