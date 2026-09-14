import unittest
from unittest.mock import patch
from pathlib import Path
from dotenv import dotenv_values

from pydantic import ValidationError
from app.core.config import Settings


class ConfigTests(unittest.TestCase):
    def make_settings(self, **kwargs):
        fixture = Path(__file__).resolve().parents[2] / ".env.example"
        return Settings(_env_file=fixture, **kwargs)

    def test_environment_overrides_operational_settings(self):
        with patch.dict("os.environ", {"SUBMIT_LIMIT": "7", "CHAT_MODEL": "test-model",
                                       "CORS_ORIGINS_CSV": "https://one.example, https://two.example"}):
            settings = self.make_settings()
        self.assertEqual(settings.submit_limit, 7)
        self.assertEqual(settings.chat_model, "test-model")
        self.assertEqual(settings.cors_origins, ["https://one.example", "https://two.example"])

    def test_invalid_budgets_fail_at_startup(self):
        for values in ({"submit_limit": 0}, {"target_chunk_chars": 900, "max_chunk_chars": 800},
                       {"analysis_timeout_seconds": 300, "vidora_function_timeout_seconds": 300},
                       {"qa_page_size": 101, "qa_max_page_size": 100}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.make_settings(**values)

    def test_operational_values_have_no_defaults(self):
        fields = Settings.model_fields
        for name in ("ai_enabled", "chat_model", "submit_limit", "cors_origins_csv"):
            self.assertTrue(fields[name].is_required(), name)

    def test_missing_setting_is_rejected(self):
        fixture = Path(__file__).resolve().parents[2] / ".env.example"
        values = {key.lower(): value for key, value in dotenv_values(fixture).items()}
        values.pop("chat_model")
        values["youtube_cookie_secret_ids"] = []
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValidationError):
            Settings(_env_file=None, **values)
