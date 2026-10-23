"""Quota windows must prevent one video from consuming account capacity too fast."""
from datetime import datetime, timedelta, timezone
import unittest

from app.core.config import settings
from app.integration.stt_quota import _wait_for_capacity


class SttQuotaTests(unittest.TestCase):
    def test_request_and_audio_windows(self):
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        recent = now - timedelta(seconds=5)
        self.assertEqual(_wait_for_capacity([(recent, 10)] * 19, now, 10), 55)
        self.assertEqual(_wait_for_capacity([(recent, 240)] * 30, now, 240), 3595)
        self.assertEqual(_wait_for_capacity([(recent, 240)] * 120, now, 240), 86395)

    def test_free_share_keeps_headroom_for_paid_videos(self):
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        # 80% of the daily audio budget used earlier today, spread over past
        # hours so only the daily window is under pressure.
        requests = int(settings.stt_audio_seconds_per_day * 0.8) // 240
        used = [(now - timedelta(hours=2, seconds=i * 60), 240) for i in range(requests)]
        free_wait = _wait_for_capacity(used, now, 240, share=0.8)
        paid_wait = _wait_for_capacity(used, now, 240, share=1.0)
        self.assertGreater(free_wait, 0)
        self.assertEqual(paid_wait, 0)

    def test_expired_reservations_do_not_consume_capacity(self):
        now = datetime(2026, 9, 23, tzinfo=timezone.utc)
        old = now - timedelta(days=1, seconds=1)
        self.assertEqual(_wait_for_capacity([(old, 240)] * 120, now, 240), 0)
