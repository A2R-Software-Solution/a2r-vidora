"""Quota windows must prevent one video from consuming account capacity too fast."""
from datetime import datetime, timedelta, timezone
import unittest

from app.integration.stt_quota import _wait_for_capacity


class SttQuotaTests(unittest.TestCase):
    def test_request_and_audio_windows(self):
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        recent = now - timedelta(seconds=5)
        self.assertEqual(_wait_for_capacity([(recent, 10)] * 19, now, 10), 55)
        self.assertEqual(_wait_for_capacity([(recent, 240)] * 30, now, 240), 3595)
        self.assertEqual(_wait_for_capacity([(recent, 240)] * 120, now, 240), 86395)

    def test_expired_reservations_do_not_consume_capacity(self):
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        old = now - timedelta(days=1, seconds=1)
        self.assertEqual(_wait_for_capacity([(old, 240)] * 120, now, 240), 0)
