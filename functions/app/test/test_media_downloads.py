"""Offline Media Downloader checks: pricing, URL rules, the ownership gate and
yt-dlp format strings. No YouTube requests, cloud calls or database writes."""
import unittest
import uuid

from pydantic import ValidationError

from app.pipeline.media_formats import QUALITIES, get_quality, media_credit_cost, ytdlp_format
from app.schemas.media_download_schema import DownloadRequest, PreviewRequest, normalize_media_url
from app.services.credit_service import media_download_reservation_key
from app.services.media_download_service import quality_options

SHORT = "https://youtube.com/shorts/UWvgHqCegNs?si=DSMIHyb6eV6I_DqX"
WATCH = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class PricingTests(unittest.TestCase):
    def test_every_started_minute_is_charged_at_the_quality_rate(self):
        self.assertEqual(media_credit_cost(get_quality("mp3_128"), 60), 1)
        self.assertEqual(media_credit_cost(get_quality("mp3_128"), 61), 2)
        self.assertEqual(media_credit_cost(get_quality("mp3_256"), 180), 6)
        self.assertEqual(media_credit_cost(get_quality("mp4_1080"), 90), 8)
        self.assertEqual(media_credit_cost(get_quality("mp4_144"), 1), 1)

    def test_higher_quality_never_costs_less(self):
        video = ["mp4_144", "mp4_240", "mp4_360", "mp4_480", "mp4_720", "mp4_1080"]
        costs = [media_credit_cost(get_quality(code), 600) for code in video]
        self.assertEqual(costs, sorted(costs))

    def test_empty_media_is_rejected(self):
        with self.assertRaises(ValueError):
            media_credit_cost(get_quality("mp3_128"), 0)

    def test_unknown_quality_is_rejected(self):
        with self.assertRaises(ValueError):
            get_quality("mp4_4320")

    def test_options_list_every_quality_with_its_cost(self):
        options = quality_options(120)
        self.assertEqual({o["code"] for o in options}, set(QUALITIES))
        by_code = {o["code"]: o["credit_cost"] for o in options}
        self.assertEqual(by_code["mp4_1080"], 8)
        self.assertEqual(by_code["mp3_48"], 2)


class FormatTests(unittest.TestCase):
    def test_video_selection_stops_at_the_quality_height(self):
        self.assertIn("height<=720", ytdlp_format(get_quality("mp4_720")))
        self.assertIn("height<=144", ytdlp_format(get_quality("mp4_144")))

    def test_audio_uses_best_audio_stream(self):
        self.assertEqual(ytdlp_format(get_quality("mp3_256")), "bestaudio/best")


class UrlTests(unittest.TestCase):
    def test_shorts_link_becomes_a_watch_link(self):
        self.assertEqual(normalize_media_url(SHORT), "https://www.youtube.com/watch?v=UWvgHqCegNs")

    def test_short_host_and_watch_links_are_accepted(self):
        self.assertEqual(normalize_media_url("https://youtu.be/dQw4w9WgXcQ"), WATCH)
        self.assertEqual(normalize_media_url(WATCH + "&t=42"), WATCH)

    def test_other_hosts_are_rejected(self):
        for bad in ("https://evil.example/watch?v=dQw4w9WgXcQ", "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "https://www.youtube.com/playlist?list=PL123"):
            with self.assertRaises(ValueError):
                normalize_media_url(bad)
            with self.assertRaises(ValidationError):
                PreviewRequest(url=bad)


class OwnershipGateTests(unittest.TestCase):
    def test_download_needs_the_rights_checkbox(self):
        with self.assertRaises(ValidationError):
            DownloadRequest(url=WATCH, quality="mp3_128", rights_confirmed=False)
        with self.assertRaises(ValidationError):
            DownloadRequest(url=WATCH, quality="mp3_128")

    def test_download_with_rights_and_known_quality_is_valid(self):
        request = DownloadRequest(url=SHORT, quality="mp4_720", rights_confirmed=True)
        self.assertEqual(request.url, "https://www.youtube.com/watch?v=UWvgHqCegNs")

    def test_unknown_quality_is_rejected(self):
        with self.assertRaises(ValidationError):
            DownloadRequest(url=WATCH, quality="mp4_8k", rights_confirmed=True)

    def test_unavailable_quality_is_listed_but_cannot_be_downloaded(self):
        self.assertFalse(get_quality("mp4_1080").available)
        self.assertIn("mp4_1080", {o["code"] for o in quality_options(60) if not o["available"]})
        with self.assertRaises(ValidationError):
            DownloadRequest(url=WATCH, quality="mp4_1080", rights_confirmed=True)
        DownloadRequest(url=WATCH, quality="mp4_720", rights_confirmed=True)


class ReservationKeyTests(unittest.TestCase):
    def test_each_attempt_holds_separately(self):
        download_id = uuid.uuid4()
        first, second = uuid.uuid4(), uuid.uuid4()
        self.assertNotEqual(media_download_reservation_key(download_id, first),
                            media_download_reservation_key(download_id, second))


if __name__ == "__main__":
    unittest.main()
