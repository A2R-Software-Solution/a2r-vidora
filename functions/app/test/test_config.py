import unittest
from unittest.mock import patch

from pydantic import ValidationError
from app.core.config import Settings


class ConfigTests(unittest.TestCase):
    def make_settings(self, **kwargs):
        return Settings(_env_file=None, environment="development", app_name="test",
                        video_retention_hours=24, pool_pre_ping=True, pool_size=1,
                        max_overflow=0, pool_recycle=60, **kwargs)

    def test_environment_overrides_operational_settings(self):
        with patch.dict("os.environ", {"SUBMIT_LIMIT": "7", "CHAT_MODEL": "test-model",
                                       "CORS_ORIGINS_CSV": "https://one.example, https://two.example"}):
            settings = self.make_settings()
        self.assertEqual(settings.submit_limit, 7)
        self.assertEqual(settings.chat_model, "test-model")
        self.assertEqual(settings.cors_origins, ["https://one.example", "https://two.example"])

    def test_invalid_budgets_fail_at_startup(self):
        for values in ({"submit_limit": 0}, {"target_chunk_chars": 900, "max_chunk_chars": 800},
                       {"analysis_timeout_seconds": 300, "function_timeout_seconds": 300},
                       {"qa_page_size": 101, "qa_max_page_size": 100}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.make_settings(**values)
