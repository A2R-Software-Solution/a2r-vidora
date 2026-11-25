"""Admin panel API: access control with mocked services."""
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch


class AdminApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app.core.rate_limit import limiter
        from app.deps import get_current_user_id, get_db
        from app.main import app
        from app.routes import admin_routes
        limiter.reset()
        self.addCleanup(limiter.reset)
        self.user_id = None
        self.user = None

        async def current():
            return self.user_id

        async def db():
            yield Mock()
        app.dependency_overrides[get_current_user_id] = current
        app.dependency_overrides[get_db] = db
        self.addCleanup(app.dependency_overrides.clear)
        self.admin = Mock(overview=AsyncMock(return_value={"users_total": 1}),
                          adjust_credits=AsyncMock(return_value=130))
        patcher = patch.object(admin_routes, "AdminService", Mock(return_value=self.admin))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings_rows = [{"key": "user_monthly_credits", "value": 30}]
        for name in ("describe", "update"):
            patcher = patch.object(admin_routes.runtime_settings, name, AsyncMock(return_value=self.settings_rows))
            setattr(self, f"settings_{name}", patcher.start())
            self.addCleanup(patcher.stop)
        repo = patch("app.deps.UserRepository", Mock(return_value=Mock(get_by_id=AsyncMock(side_effect=lambda _: self.user))))
        repo.start()
        self.addCleanup(repo.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def as_user(self, *, is_admin):
        self.user_id = uuid.uuid4()
        self.user = Mock(id=self.user_id, email="boss@test.local", is_admin=is_admin)

    def test_guests_get_401(self):
        self.assertEqual(self.client.get("/admin/overview").status_code, 401)
        self.admin.overview.assert_not_awaited()

    def test_non_admins_get_403_everywhere(self):
        self.as_user(is_admin=False)
        for path in ("/admin/overview", "/admin/users", "/admin/payments", "/admin/videos",
                     "/admin/shorts", "/admin/qa-logs", f"/admin/users/{uuid.uuid4()}"):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        response = self.client.post(f"/admin/users/{uuid.uuid4()}/credits", json={"amount": 5, "reason": "gift"})
        self.assertEqual(response.status_code, 403)
        self.admin.adjust_credits.assert_not_awaited()
        self.assertEqual(self.client.get("/admin/settings").status_code, 403)
        response = self.client.put("/admin/settings", json={"values": {"user_monthly_credits": 30}})
        self.assertEqual(response.status_code, 403)
        self.settings_update.assert_not_awaited()

    def test_access_check_admits_only_admins(self):
        self.assertEqual(self.client.get("/admin/me").status_code, 401)
        self.as_user(is_admin=False)
        self.assertEqual(self.client.get("/admin/me").status_code, 403)
        self.as_user(is_admin=True)
        self.assertEqual(self.client.get("/admin/me").json(), {"is_admin": True})

    def test_admin_reads_and_saves_settings(self):
        self.as_user(is_admin=True)
        self.assertEqual(self.client.get("/admin/settings").json(), self.settings_rows)
        response = self.client.put("/admin/settings", json={"values": {"user_monthly_credits": 30, "short_credit_cost": None}})
        self.assertEqual((response.status_code, response.json()), (200, self.settings_rows))
        values, email = self.settings_update.await_args.args[1:]
        self.assertEqual((values, email), ({"user_monthly_credits": 30, "short_credit_cost": None}, "boss@test.local"))

    def test_invalid_settings_are_rejected(self):
        from app.services.runtime_settings import InvalidSettingError
        self.as_user(is_admin=True)
        self.assertEqual(self.client.put("/admin/settings", json={"values": {}}).status_code, 422)
        self.assertEqual(self.client.put("/admin/settings", json={"values": {"user_monthly_credits": "many"}}).status_code, 422)
        self.settings_update.side_effect = InvalidSettingError("Unknown setting: database_url")
        response = self.client.put("/admin/settings", json={"values": {"database_url": 1}})
        self.assertEqual((response.status_code, response.json()["detail"]), (422, "Unknown setting: database_url"))

    def test_admin_can_read_overview(self):
        self.as_user(is_admin=True)
        response = self.client.get("/admin/overview")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"users_total": 1})

    def test_non_admins_cannot_read_credits_summary(self):
        self.as_user(is_admin=False)
        self.assertEqual(self.client.get("/admin/credits-summary").status_code, 403)

    def test_admin_can_read_credits_summary(self):
        self.as_user(is_admin=True)
        self.admin.credits_summary = AsyncMock(return_value={"free_bonus_per_user": 40})
        response = self.client.get("/admin/credits-summary")
        self.assertEqual((response.status_code, response.json()), (200, {"free_bonus_per_user": 40}))

    def test_adjust_records_admin_email_and_returns_balance(self):
        self.as_user(is_admin=True)
        target = uuid.uuid4()
        response = self.client.post(f"/admin/users/{target}/credits", json={"amount": 30, "reason": "support gift"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["purchased_balance"], 130)
        self.admin.adjust_credits.assert_awaited_once_with(target, 30, "support gift", "boss@test.local")

    def test_adjust_rejects_zero_and_missing_reason(self):
        self.as_user(is_admin=True)
        url = f"/admin/users/{uuid.uuid4()}/credits"
        self.assertEqual(self.client.post(url, json={"amount": 0, "reason": "nothing"}).status_code, 422)
        self.assertEqual(self.client.post(url, json={"amount": 5, "reason": ""}).status_code, 422)

    def test_unknown_user_is_404(self):
        self.as_user(is_admin=True)
        self.admin.adjust_credits.return_value = None
        response = self.client.post(f"/admin/users/{uuid.uuid4()}/credits", json={"amount": 5, "reason": "gift"})
        self.assertEqual(response.status_code, 404)

    def test_invalid_filters_are_rejected(self):
        self.as_user(is_admin=True)
        self.assertEqual(self.client.get("/admin/videos?status=bogus").status_code, 422)
        self.assertEqual(self.client.get("/admin/users?limit=5000").status_code, 422)


class RuntimeSettingsTests(unittest.TestCase):
    def setUp(self):
        from app.services import runtime_settings
        self.rs = runtime_settings
        self.addCleanup(runtime_settings.apply, {})

    def test_overrides_apply_and_removing_one_restores_the_default(self):
        from app.core.config import settings
        from app.services.payment_service import credit_packs
        default = self.rs.DEFAULTS["user_monthly_credits"]
        self.rs.apply({"user_monthly_credits": 30, "pack_pro_credits": 900, "pack_pro_amount_cents": 1200})
        self.assertEqual(settings.user_monthly_credits, 30)
        pro = credit_packs()["pro"]
        self.assertEqual((pro.credits, pro.amount_cents), (900, 1200))
        self.rs.apply({})
        self.assertEqual(settings.user_monthly_credits, default)
        self.assertEqual(credit_packs()["pro"].credits, self.rs.DEFAULTS["pack_pro_credits"])

    def test_stored_values_outside_the_range_or_unknown_are_ignored(self):
        from app.core.config import settings
        database_url = settings.database_url
        self.rs.apply({"short_credit_cost": 0, "database_url": 5})
        self.assertEqual(settings.short_credit_cost, self.rs.DEFAULTS["short_credit_cost"])
        self.assertEqual(settings.database_url, database_url)

    def test_only_listed_settings_within_their_range_can_be_saved(self):
        self.rs.validated({"user_monthly_credits": 0, "short_credit_cost": None})
        for values in ({"database_url": 1}, {"short_credit_cost": 0}, {"user_monthly_credits": 10_001},
                       {"pack_topup_amount_cents": 49}):
            with self.assertRaises(self.rs.InvalidSettingError, msg=values):
                self.rs.validated(values)

    def test_every_editable_setting_is_an_integer_setting_inside_its_range(self):
        for key, spec in self.rs.EDITABLE.items():
            self.assertIsInstance(self.rs.DEFAULTS[key], int, key)
            self.assertTrue(spec.minimum <= self.rs.DEFAULTS[key] <= spec.maximum, key)


class PlansApiTests(unittest.TestCase):
    def test_plans_are_public_and_reflect_current_settings(self):
        from fastapi.testclient import TestClient
        from app.core.rate_limit import limiter
        from app.main import app
        from app.services import runtime_settings
        limiter.reset()
        self.addCleanup(limiter.reset)
        self.addCleanup(runtime_settings.apply, {})
        runtime_settings.apply({"user_monthly_credits": 30})
        with patch.object(runtime_settings, "refresh", AsyncMock()), TestClient(app) as client:
            body = client.get("/credits/plans").json()
        self.assertEqual(body["user_monthly_credits"], 30)
        self.assertNotIn("guest_daily_credits", body)


if __name__ == "__main__":
    unittest.main()


class CreditsSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_given_and_used_are_split_by_bucket_and_net_of_refunds(self):
        from datetime import datetime
        from app.services.admin_service import AdminService

        def scalar(value):
            return Mock(scalar_one=Mock(return_value=value))

        def rows(*items):
            return Mock(all=Mock(return_value=list(items)))
        month = rows(("reserve", "free", -1, -30), ("release", "free", 1, 5), ("reserve", "purchased", -1, -20),
                     ("purchase", "purchased", 1, 300), ("adjust", "purchased", 1, 10), ("adjust", "purchased", -1, -4))
        db = Mock(execute=AsyncMock(side_effect=[scalar(6), scalar(3), rows((datetime(2026, 11, 1), 2, 420, 1000)), month, month, scalar(250)]))
        with patch("app.services.admin_service.settings", Mock(user_monthly_credits=40)):
            result = await AdminService(db).credits_summary()
        this_month = result["this_month"]
        self.assertEqual((this_month["free_given"], this_month["free_used"], this_month["purchased_used"]), (120, 25, 20))
        self.assertEqual((this_month["purchased_given"], this_month["admin_added"], this_month["taken_back"]), (300, 10, 4))
        self.assertEqual((this_month["total_given"], this_month["total_used"]), (430, 45))
        self.assertEqual(result["all_time"]["free_given"], 240)
        self.assertEqual(result["sales_by_month"], [{"month": "2026-11-01", "payments": 2, "credits_sold": 420, "revenue_cents": 1000}])
        self.assertEqual((result["free_bonus_per_user"], result["purchased_outstanding"]), (40, 250))
