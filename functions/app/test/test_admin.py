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

    def test_admin_can_read_overview(self):
        self.as_user(is_admin=True)
        response = self.client.get("/admin/overview")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"users_total": 1})

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


if __name__ == "__main__":
    unittest.main()
