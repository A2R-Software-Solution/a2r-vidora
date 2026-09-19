"""HTTP-level limiter regression tests. No external services are called."""
import ast
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

from fastapi import Request
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.rate_limit import client_key, limiter
from app.deps import get_current_user_id, get_db
from app.controller import video_controller, qa_log_controller, user_controller


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        limiter.reset()
        self.user = None
        async def user():
            return self.user
        async def db():
            yield None
        app.dependency_overrides[get_current_user_id] = user
        app.dependency_overrides[get_db] = db
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(limiter.reset)
        for name, value in [("rate_limit_trusted_proxy_hops", 1)]:
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        now = datetime.now(timezone.utc)
        video = SimpleNamespace(id=uuid.uuid4(), user_id=None, youtube_id="yYF2Vf1Gc14",
            youtube_url="https://youtu.be/yYF2Vf1Gc14", title="Example", duration=60,
            status="completed", summary="Summary", created_at=now, expires_at=now + timedelta(days=1))
        log = SimpleNamespace(id=uuid.uuid4(), video_id=video.id, user_id=None,
            question="Why?", answer="Answer", created_at=now)
        account = SimpleNamespace(id=uuid.uuid4(), firebase_uid="a" * 24,
            email="test@example.com", plan="free", created_at=now)
        submit = AsyncMock(return_value=(video, False))
        self.mocks = {"submit_video": submit}
        services = [
            (video_controller, "VideoService", Mock(submit_once=submit,
                get_for_user=AsyncMock(return_value=video), list_for_user=AsyncMock(return_value=[video]))),
            (qa_log_controller, "QALogService", Mock(ask=AsyncMock(return_value=log),
                list_for_video=AsyncMock(return_value=([log], 1)))),
            (user_controller, "UserService", Mock(get_or_create=AsyncMock(return_value=account),
                get_by_id=AsyncMock(return_value=account))),
        ]
        for module, name, service in services:
            patcher = patch.object(module, name, return_value=service)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(video_controller, "verify_recaptcha", AsyncMock())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def send(self, method, path, body=None, ip="198.51.100.1"):
        return self.client.request(method, path, json=body,
            headers={"X-Forwarded-For": ip, "Origin": settings.cors_origins[0]})

    def test_every_route_enforces_its_budget(self):
        identifier = uuid.uuid4()
        cases = [
            ("POST", "/videos/analyze", {"youtube_url": "https://youtu.be/yYF2Vf1Gc14"}, settings.submit_limit),
            ("GET", f"/videos?video_id={identifier}", None, 50),
            ("POST", f"/videos/{identifier}/qa/ask", {"question": "Why?"}, settings.question_limit),
            ("GET", f"/videos/{identifier}/qa", None, 50),
            ("POST", "/users", {"firebase_uid": "a" * 24, "email": "test@example.com"}, 10),
            ("GET", f"/users/{identifier}", None, 50),
            ("GET", "/health", None, 50),
            ("GET", "/ping", None, 50),
        ]
        for method, path, body, budget in cases:
            with self.subTest(path=path):
                limiter.reset()
                for _ in range(budget):
                    response = self.send(method, path, body)
                    self.assertEqual(response.status_code, 200, response.text)
                response = self.send(method, path, body)
                self.assertEqual(response.status_code, 429, response.text)
                self.assertIn("detail", response.json())
                self.assertGreater(int(response.headers["retry-after"]), 0)
                self.assertEqual(response.headers["x-ratelimit-remaining"], "0")
                self.assertIn("Retry-After", response.headers["access-control-expose-headers"])

    def test_different_ips_are_independent_and_spoofed_prefix_does_not_reset(self):
        body = {"youtube_url": "https://youtu.be/yYF2Vf1Gc14"}
        for _ in range(settings.submit_limit):
            self.assertEqual(self.send("POST", "/videos/analyze", body).status_code, 200)
        self.assertEqual(self.send("POST", "/videos/analyze", body,
            ip="203.0.113.9, 198.51.100.1").status_code, 429)
        self.assertEqual(self.send("POST", "/videos/analyze", body,
            ip="198.51.100.2").status_code, 200)
        self.assertEqual(self.mocks["submit_video"].await_count, settings.submit_limit + 1)

    def test_question_budget_spans_videos_and_accounts_are_independent(self):
        self.user = uuid.uuid4()
        for _ in range(settings.question_limit):
            self.assertEqual(self.send("POST", f"/videos/{uuid.uuid4()}/qa/ask",
                {"question": "Why?"}).status_code, 200)
        self.assertEqual(self.send("POST", f"/videos/{uuid.uuid4()}/qa/ask",
            {"question": "Why?"}, ip="198.51.100.2").status_code, 429)
        self.user = uuid.uuid4()
        self.assertEqual(self.send("POST", f"/videos/{uuid.uuid4()}/qa/ask",
            {"question": "Why?"}).status_code, 200)

    def test_window_expiration_allows_requests_again(self):
        body = {"youtube_url": "https://youtu.be/yYF2Vf1Gc14"}
        with patch("limits.storage.memory.time.time", return_value=1000):
            for _ in range(settings.submit_limit):
                self.assertEqual(self.send("POST", "/videos/analyze", body).status_code, 200)
            self.assertEqual(self.send("POST", "/videos/analyze", body).status_code, 429)
        with patch("limits.storage.memory.time.time", return_value=1001 + settings.submit_window_seconds):
            self.assertEqual(self.send("POST", "/videos/analyze", body).status_code, 200)

    def test_direct_requests_ignore_untrusted_forwarding(self):
        request = Request({"type": "http", "client": ("192.0.2.1", 123),
            "headers": [(b"x-forwarded-for", b"198.51.100.1")]})
        with patch.object(settings, "rate_limit_trusted_proxy_hops", 0):
            self.assertEqual(client_key(request), "ip:192.0.2.1")

    def test_warmup_bypasses_asgi_and_does_not_consume_budget(self):
        # Execute only the real Firebase entrypoint body, avoiding SDK startup.
        source = Path(__file__).resolve().parents[2] / "main.py"
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "api")
        function.decorator_list = []
        function.returns = None
        for arg in function.args.args:
            arg.annotation = None
        from types import SimpleNamespace
        from unittest.mock import Mock
        warm = AsyncMock()
        response = Mock()
        import asyncio
        namespace = {"asyncio": asyncio, "_warm_reusable_resources": warm,
                     "https_fn": SimpleNamespace(Response=response), "_wsgi_app": Mock()}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        for _ in range(10):
            namespace["api"](SimpleNamespace(method="POST", args={"warmup": "true"}))
        self.assertEqual(warm.await_count, 10)
        response.from_app.assert_not_called()
        body = {"youtube_url": "https://youtu.be/yYF2Vf1Gc14"}
        for _ in range(settings.submit_limit):
            self.assertEqual(self.send("POST", "/videos/analyze", body).status_code, 200)
