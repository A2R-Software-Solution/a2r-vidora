import tempfile
import unittest
from unittest.mock import patch

from app.integration import secret_manager_client as secrets
from app.pipeline import youtube_downloader as downloader


class CookieFailoverTests(unittest.TestCase):
    def setUp(self):
        secrets._cooling.clear()
        secrets._cache.clear()
        self.accounts = patch.object(downloader.settings, "youtube_cookie_secret_ids", ["a", "b"])
        self.accounts.start()
        self.addCleanup(self.accounts.stop)
        self.addCleanup(secrets._cooling.clear)

    def run_body(self, body, stored):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(secrets, "_get_cached_secret", side_effect=lambda s: stored[s]), \
                patch.object(secrets, "update_youtube_cookie") as update:
            try:
                return downloader.with_cookie_failover(directory, body), update
            except downloader.YouTubeBotChallengeError as exc:
                return exc, update

    def test_refused_account_is_replaced_by_the_next(self):
        used = []

        def body(path):
            used.append(open(path).read())
            if used[-1] == "bad":
                raise downloader.YouTubeBotChallengeError("refused")
            return "ok"

        result, update = self.run_body(body, {"a": "bad", "b": "good"})
        self.assertEqual(result, "ok")
        self.assertEqual(sorted(used), ["bad", "good"] if len(used) == 2 else ["good"])
        update.assert_not_called()

    def test_all_accounts_refused_raises_and_saves_nothing(self):
        def body(path):
            with open(path, "w") as handle:
                handle.write("degraded")
            raise downloader.YouTubeBotChallengeError("refused")

        result, update = self.run_body(body, {"a": "x", "b": "y"})
        self.assertIsInstance(result, downloader.YouTubeBotChallengeError)
        update.assert_not_called()
        self.assertEqual(set(secrets._cooling), {"a", "b"})

    def test_refreshed_cookies_are_saved_after_success(self):
        def body(path):
            with open(path, "w") as handle:
                handle.write("fresh")
            return "ok"

        result, update = self.run_body(body, {"a": "old", "b": "old"})
        self.assertEqual(result, "ok")
        update.assert_called_once()
        self.assertEqual(update.call_args.args[1], "fresh")

    def test_refused_account_is_skipped_and_its_cache_dropped(self):
        secrets._cache["a"] = secrets._CacheEntry("stale", 0)
        secrets.report_bad_youtube_cookie("a")
        self.assertNotIn("a", secrets._cache)
        with patch.object(secrets, "_get_cached_secret", return_value="c"):
            picks = {secrets.get_youtube_cookie()[0] for _ in range(20)}
        self.assertEqual(picks, {"b"})


if __name__ == "__main__":
    unittest.main()


class PotProviderArgsTests(unittest.TestCase):
    def test_disabled_without_url(self):
        with patch.object(downloader.settings, "pot_provider_url", None):
            self.assertEqual(downloader.pot_extractor_args(), {})
            self.assertEqual(downloader.pot_cli_args(), [])

    def test_url_is_passed_to_yt_dlp_in_both_forms(self):
        with patch.object(downloader.settings, "pot_provider_url", " https://pot.example.run.app "):
            self.assertEqual(downloader.pot_extractor_args(),
                             {"youtubepot-bgutilhttp": {"base_url": ["https://pot.example.run.app"]}})
            self.assertEqual(downloader.pot_cli_args(),
                             ["--extractor-args", "youtubepot-bgutilhttp:base_url=https://pot.example.run.app"])
