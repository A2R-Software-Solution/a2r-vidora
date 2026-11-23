"""Banning a user: enforcement on every request, the message they see, and the admin controls."""
import unittest
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.deps import AccountBannedError, get_current_user_id
from app.services.admin_service import AdminBanError, AdminService


class EnforcementTests(unittest.IsolatedAsyncioTestCase):
    async def _resolve(self, user):
        repo = Mock(get_by_firebase_uid=AsyncMock(return_value=user))
        with patch("app.deps._ensure_firebase_initialized"), \
             patch("app.deps.firebase_auth.verify_id_token", return_value={"uid": "abc"}), \
             patch("app.deps.UserRepository", return_value=repo):
            return await get_current_user_id("Bearer token", Mock())

    async def test_a_banned_account_is_refused_with_its_reason(self):
        banned = SimpleNamespace(id=uuid.uuid4(), banned_at=datetime.now(timezone.utc), ban_reason="Abuse")
        with self.assertRaises(AccountBannedError) as caught:
            await self._resolve(banned)
        self.assertEqual(caught.exception.reason, "Abuse")

    async def test_an_active_account_passes(self):
        user = SimpleNamespace(id=uuid.uuid4(), banned_at=None, ban_reason=None)
        self.assertEqual(await self._resolve(user), user.id)


class AdminServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(self, user):
        db = Mock(commit=AsyncMock(), execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=user))))
        return AdminService(db), db

    async def test_ban_stores_the_reason_and_commits(self):
        user = SimpleNamespace(id=uuid.uuid4(), is_admin=False, banned_at=None, ban_reason=None)
        service, db = self.service(user)
        self.assertTrue(await service.ban(user.id, "Spam", SimpleNamespace(id=uuid.uuid4())))
        self.assertIsNotNone(user.banned_at)
        self.assertEqual(user.ban_reason, "Spam")
        db.commit.assert_awaited_once()

    async def test_admins_and_the_acting_admin_cannot_be_banned(self):
        other_admin = SimpleNamespace(id=uuid.uuid4(), is_admin=True, banned_at=None, ban_reason=None)
        service, db = self.service(other_admin)
        with self.assertRaises(AdminBanError):
            await service.ban(other_admin.id, "x" * 5, SimpleNamespace(id=uuid.uuid4()))
        me = SimpleNamespace(id=uuid.uuid4(), is_admin=False, banned_at=None, ban_reason=None)
        service, db = self.service(me)
        with self.assertRaises(AdminBanError):
            await service.ban(me.id, "x" * 5, SimpleNamespace(id=me.id))
        db.commit.assert_not_awaited()

    async def test_unknown_user_and_unban(self):
        service, _ = self.service(None)
        self.assertFalse(await service.ban(uuid.uuid4(), "Spam", SimpleNamespace(id=uuid.uuid4())))
        self.assertFalse(await service.unban(uuid.uuid4()))
        user = SimpleNamespace(id=uuid.uuid4(), banned_at=datetime.now(timezone.utc), ban_reason="Spam")
        service, db = self.service(user)
        self.assertTrue(await service.unban(user.id))
        self.assertEqual((user.banned_at, user.ban_reason), (None, None))
        db.commit.assert_awaited_once()

    def test_user_rows_show_what_is_left_to_spend(self):
        user = SimpleNamespace(id=uuid.uuid4(), email="a@b.c", plan="free", is_admin=False,
                               banned_at=None, ban_reason=None, created_at=datetime.now(timezone.utc))
        with patch("app.services.admin_service.settings", SimpleNamespace(user_monthly_credits=80)), \
             patch("app.services.admin_service.ist_today"):
            row = AdminService._user_row(user, 30, 25, date(2026, 11, 1))
            self.assertEqual((row["purchased_balance"], row["free_left"], row["available"]), (30, 55, 85))
            # The free bonus is one-time: what was used earlier is not given back later.
            row = AdminService._user_row(user, None, 70, date(2026, 10, 1))
            self.assertEqual((row["purchased_balance"], row["free_left"], row["available"]), (0, 10, 10))
            self.assertFalse(row["banned"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app.core.rate_limit import limiter
        from app.deps import get_db
        from app.main import app
        from app.routes import admin_routes
        limiter.reset()
        self.addCleanup(limiter.reset)
        self.user_id = uuid.uuid4()
        self.user = Mock(id=self.user_id, email="boss@test.local", is_admin=True)
        self.raise_banned = False

        async def current():
            if self.raise_banned:
                raise AccountBannedError("Spamming the service")
            return self.user_id

        async def db():
            yield Mock()
        app.dependency_overrides[get_current_user_id] = current
        app.dependency_overrides[get_db] = db
        self.addCleanup(app.dependency_overrides.clear)
        self.admin = Mock(ban=AsyncMock(return_value=True), unban=AsyncMock(return_value=True))
        for target, value in (("AdminService", Mock(return_value=self.admin)),):
            patcher = patch.object(admin_routes, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        repo = patch("app.deps.UserRepository", Mock(return_value=Mock(get_by_id=AsyncMock(side_effect=lambda _: self.user))))
        repo.start()
        self.addCleanup(repo.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_a_banned_user_gets_a_403_with_the_message(self):
        self.raise_banned = True
        response = self.client.get("/credits")
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertEqual(data["code"], "account_banned")
        self.assertEqual(data["reason"], "Spamming the service")
        self.assertIn("suspended", data["detail"])

    def test_admin_bans_and_unbans(self):
        target = uuid.uuid4()
        response = self.client.post(f"/admin/users/{target}/ban", json={"reason": "  Abusing   the service "})
        self.assertEqual((response.status_code, response.json()["banned"]), (200, True))
        self.assertEqual(self.admin.ban.await_args.args[:2], (target, "Abusing the service"))
        self.assertEqual(self.client.post(f"/admin/users/{target}/unban").status_code, 200)

    def test_ban_validation_and_errors(self):
        target = uuid.uuid4()
        self.assertEqual(self.client.post(f"/admin/users/{target}/ban", json={"reason": "x"}).status_code, 422)
        self.assertEqual(self.client.post(f"/admin/users/{target}/ban", json={"reason": "x" * 301}).status_code, 422)
        self.admin.ban.side_effect = AdminBanError("Admins cannot be banned.")
        self.assertEqual(self.client.post(f"/admin/users/{target}/ban", json={"reason": "Spam"}).status_code, 409)
        self.admin.ban.side_effect = None
        self.admin.ban.return_value = False
        self.assertEqual(self.client.post(f"/admin/users/{target}/ban", json={"reason": "Spam"}).status_code, 404)
        self.admin.unban.return_value = False
        self.assertEqual(self.client.post(f"/admin/users/{target}/unban").status_code, 404)

    def test_only_admins_can_ban_and_the_route_is_rate_limited(self):
        target = uuid.uuid4()
        self.user.is_admin = False
        self.assertEqual(self.client.post(f"/admin/users/{target}/ban", json={"reason": "Spam"}).status_code, 403)
        self.admin.ban.assert_not_awaited()
        self.user.is_admin = True
        for _ in range(20):
            self.assertEqual(self.client.post(f"/admin/users/{target}/ban", json={"reason": "Spam"}).status_code, 200)
        self.assertEqual(self.client.post(f"/admin/users/{target}/ban", json={"reason": "Spam"}).status_code, 429)


if __name__ == "__main__":
    unittest.main()


class DashboardDataTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeseries_fills_missing_days_with_zero(self):
        today = datetime.now(timezone.utc).date()
        yesterday = today.fromordinal(today.toordinal() - 1)
        db = Mock(execute=AsyncMock(side_effect=lambda stmt: Mock(all=Mock(return_value=[(yesterday, 3)]))))
        data = await AdminService(db).timeseries(7)
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual(data["days"][-1], today.isoformat())
        for key in ("users", "videos", "shorts", "revenue_cents", "credits_spent"):
            self.assertEqual(len(data[key]), 7)
            self.assertEqual(data[key][-2:], [3, 0])
            self.assertEqual(sum(data[key]), 3)

    async def test_activity_merges_sources_newest_first_and_trims(self):
        now = datetime.now(timezone.utc)
        sequence = [
            [("a@b.c", now.replace(microsecond=1))],                    # users
            [("completed", now.replace(microsecond=5))],                # shorts
            [("Title", "https://youtu.be/x", now.replace(microsecond=3))],  # videos
            [("adjust", 75, "a@b.c", now.replace(microsecond=4)), ("adjust", -30, None, now.replace(microsecond=2))],
            [("short_credit_cost", "boss@x", now.replace(microsecond=6))],  # settings
        ]
        results = iter(sequence)
        db = Mock(execute=AsyncMock(side_effect=lambda stmt: Mock(all=Mock(return_value=next(results)))))
        events = await AdminService(db).activity(4)
        self.assertEqual([event["title"] for event in events],
                         ["Settings updated", "New reel created", "Credits added (75)", "Video analysed"])

    def test_dashboard_routes_need_an_admin_and_validate_the_range(self):
        from fastapi.testclient import TestClient
        from app.core.rate_limit import limiter
        from app.deps import get_current_user_id, get_db
        from app.main import app
        from app.routes import admin_routes
        limiter.reset()
        admin_id = uuid.uuid4()
        user = Mock(id=admin_id, email="boss@test.local", is_admin=False)

        async def current():
            return admin_id

        async def db():
            yield Mock()
        app.dependency_overrides[get_current_user_id] = current
        app.dependency_overrides[get_db] = db
        service = Mock(timeseries=AsyncMock(return_value={"days": []}), activity=AsyncMock(return_value=[]))
        try:
            with patch.object(admin_routes, "AdminService", Mock(return_value=service)), \
                 patch("app.deps.UserRepository", Mock(return_value=Mock(get_by_id=AsyncMock(return_value=user)))), \
                 TestClient(app) as client:
                self.assertEqual(client.get("/admin/timeseries").status_code, 403)
                self.assertEqual(client.get("/admin/activity").status_code, 403)
                user.is_admin = True
                self.assertEqual(client.get("/admin/timeseries?days=30").status_code, 200)
                self.assertEqual(client.get("/admin/timeseries?days=3").status_code, 422)
                self.assertEqual(client.get("/admin/timeseries?days=500").status_code, 422)
                self.assertEqual(client.get("/admin/activity?limit=99").status_code, 422)
                self.assertEqual(client.get("/admin/activity").status_code, 200)
        finally:
            app.dependency_overrides.clear()
            limiter.reset()
