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
             patch("app.services.admin_service.month_start", return_value=date(2026, 11, 1)), \
             patch("app.services.admin_service.ist_today"):
            row = AdminService._user_row(user, 30, 25, date(2026, 11, 1))
            self.assertEqual((row["purchased_balance"], row["free_left"], row["available"]), (30, 55, 85))
            # A new month: the free allowance is whole again, whatever was used last month.
            row = AdminService._user_row(user, None, 70, date(2026, 10, 1))
            self.assertEqual((row["purchased_balance"], row["free_left"], row["available"]), (0, 80, 80))
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
