import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.governance.runtime import (
    CALLS, GovernanceBlocked, Policy, enforce, get_policy, governed,
)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = Policy(version="test", owner="reviewer", approved=True,
                             deployment_regions=["eu"], evaluated_languages=["en"],
                             operations={"answer": "test-model"})

    def check(self, **overrides):
        args = dict(production=True, region="eu", enabled=True)
        args.update(overrides)
        enforce(self.policy, "answer", "test-model", **args)

    def test_approved_region(self):
        self.check()

    def test_unknown_region(self):
        with self.assertRaises(GovernanceBlocked):
            self.check(region="unknown")

    def test_unapproved_production(self):
        self.policy = self.policy.model_copy(update={"approved": False})
        with self.assertRaises(GovernanceBlocked):
            self.check()
        self.check(production=False)

    def test_unassigned_owner(self):
        self.policy = self.policy.model_copy(update={"owner": "unassigned"})
        with self.assertRaises(GovernanceBlocked):
            self.check()

    def test_kill_switch_also_blocks_development(self):
        with self.assertRaises(GovernanceBlocked):
            self.check(production=False, enabled=False)

    def test_inventory_mismatch(self):
        with self.assertRaises(GovernanceBlocked):
            enforce(self.policy, "answer", "new-model", production=False, region="", enabled=True)

    def test_bundled_policy_unapproved(self):
        get_policy.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(get_policy().approved)
        get_policy.cache_clear()


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = SimpleNamespace(is_production=False, ai_enabled=True, ai_deployment_region="")
        self.config = patch.dict("sys.modules", {"app.core.config": SimpleNamespace(settings=self.settings)})
        self.config.start()
        self.addCleanup(self.config.stop)
        self.env = patch.dict(os.environ, {"AI_EMERGENCY_STOP": "false"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.policy = Policy(version="test", owner="reviewer", approved=True,
                             deployment_regions=["eu"], evaluated_languages=["en"],
                             operations={"answer": "test-model"})
        self.loader = patch("app.governance.runtime.get_policy", return_value=self.policy)
        self.loader.start()
        self.addCleanup(self.loader.stop)

    async def test_blocked_call_never_executes(self):
        called = False

        @governed("answer", "unapproved")
        async def model():
            nonlocal called
            called = True

        with self.assertRaises(GovernanceBlocked):
            await model()
        self.assertFalse(called)

    async def test_emergency_stop(self):
        @governed("answer", "test-model")
        async def model():
            self.fail("Model must not execute")

        with patch.dict(os.environ, {"AI_EMERGENCY_STOP": "true"}):
            with self.assertRaises(GovernanceBlocked):
                await model()

    async def test_invalid_policy_fails_closed(self):
        @governed("answer", "test-model")
        async def model():
            self.fail("Model must not execute")

        with patch("app.governance.runtime.get_policy", side_effect=ValueError("sensitive policy")):
            with self.assertRaisesRegex(GovernanceBlocked, "unavailable or invalid"):
                await model()

    async def test_success_records_metadata_only(self):
        @governed("answer", "test-model")
        async def model(question):
            return "private answer"

        counter = CALLS.labels("answer", "success")
        before = counter._value.get()
        with self.assertLogs("vidora.governance", level="INFO") as captured:
            self.assertEqual(await model("private question"), "private answer")
        event = json.loads(captured.records[0].getMessage())
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(event["policy_version"], "test")
        self.assertNotIn("private", captured.output[0])
        self.assertEqual(counter._value.get(), before + 1)

    async def test_exception_is_preserved_without_logging_payload(self):
        @governed("answer", "test-model")
        async def model():
            raise RuntimeError("sensitive provider payload")

        with self.assertLogs("vidora.governance", level="INFO") as captured:
            with self.assertRaises(RuntimeError):
                await model()
        self.assertNotIn("sensitive", captured.output[0])
        self.assertEqual(json.loads(captured.records[0].getMessage())["outcome"], "error")

    async def test_cancellation_is_recorded(self):
        @governed("answer", "test-model")
        async def model():
            raise asyncio.CancelledError()

        with self.assertLogs("vidora.governance", level="INFO") as captured:
            with self.assertRaises(asyncio.CancelledError):
                await model()
        self.assertEqual(json.loads(captured.records[0].getMessage())["outcome"], "cancelled")
