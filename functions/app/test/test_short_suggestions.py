import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from groq import BadRequestError

from app.integration import groq_client
from app.integration.groq_client import GroqRequestError, generate_short_suggestions

GOOD = json.dumps({"suggestions": [
    {"title": "A", "hook": "h", "start_time": 10, "end_time": 40, "reason": "r"},
    {"title": "B", "hook": "h", "start_time": 50, "end_time": 90, "reason": "r"},
    {"title": "C", "hook": "h", "start_time": 100, "end_time": 130, "reason": "r"},
]})


def _response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None)


def _bad_request():
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return BadRequestError("bad", response=httpx.Response(400, request=request),
                           body={"error": {"code": "json_validate_failed"}})


class ShortSuggestionTests(unittest.IsolatedAsyncioTestCase):
    def _patch(self, outcomes):
        create = AsyncMock(side_effect=outcomes)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        async def fake_with_client(operation, **_):
            return await operation(client)

        patcher = patch.object(groq_client, "_with_groq_client", fake_with_client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return create

    async def test_first_call_leaves_room_for_reasoning_and_requests_json(self):
        create = self._patch([_response(GOOD)])
        result = await generate_short_suggestions("[0-10] hello")
        self.assertEqual(len(result), 2)
        kwargs = create.await_args.kwargs
        self.assertGreaterEqual(kwargs["max_tokens"], 2000)
        self.assertEqual(kwargs["reasoning_effort"], "low")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})

    async def test_rejected_request_is_retried_without_json_mode(self):
        create = self._patch([_bad_request(), _response(GOOD)])
        with self.assertLogs(level="ERROR") as logs:
            result = await generate_short_suggestions("[0-10] hello")
        self.assertEqual(len(result), 2)
        self.assertEqual(create.await_count, 2)
        retry = create.await_args_list[1].kwargs
        self.assertNotIn("response_format", retry)
        self.assertNotIn("reasoning_effort", retry)
        self.assertTrue(any("rejected" in line for line in logs.output))

    async def test_second_rejection_surfaces_as_provider_error(self):
        create = self._patch([_bad_request(), _bad_request()])
        with self.assertLogs(level="ERROR"), self.assertRaises(GroqRequestError):
            await generate_short_suggestions("[0-10] hello")
        self.assertEqual(create.await_count, 2)


if __name__ == "__main__":
    unittest.main()
