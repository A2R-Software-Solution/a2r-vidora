"""Offline Song Merger checks: no cloud uploads, YouTube requests or production DB writes."""
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException
from pydantic import ValidationError
from app.core.config import settings
from app.pipeline.audio_merger import MergeError, build_merge_command, merge_audio
from app.schemas.audio_merge_schema import AudioMergeRequest, AudioMergeResponse
from app.services.audio_merge_service import AudioMergeService, upload_extension
from app.services.credit_service import (
    CreditOwner, InsufficientCreditsError, audio_merge_credit_cost, audio_merge_reservation_key)

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def yt(start, end):
    return {"source": "youtube", "url": URL, "start_time": start, "end_time": end}


def up(index, start, end):
    return {"source": "upload", "file_index": index, "start_time": start, "end_time": end}


class CostTests(unittest.TestCase):
    def test_cost_is_started_minutes_plus_fee_per_extra_track(self):
        self.assertEqual(audio_merge_credit_cost([100, 75]), 3 + 1)   # 175s -> 3 min, 2 tracks
        self.assertEqual(audio_merge_credit_cost([240, 240]), 8 + 1)
        self.assertEqual(audio_merge_credit_cost([60] * 5), 5 + 4)
        self.assertEqual(audio_merge_credit_cost([1, 1]), 1 + 1)

    def test_rejects_empty_segments(self):
        for bad in ([], [0, 30], [-5, 30]):
            with self.assertRaises(ValueError):
                audio_merge_credit_cost(bad)


class SchemaTests(unittest.TestCase):
    def test_valid_request(self):
        request = AudioMergeRequest(tracks=[yt(60, 160), up(0, 0, 75)], crossfade_seconds=2)
        self.assertEqual([t.seconds for t in request.tracks], [100, 75])

    def test_invalid_requests(self):
        cases = {
            "single track": dict(tracks=[yt(0, 30)]),
            "too many tracks": dict(tracks=[yt(0, 30)] * (settings.audio_merge_max_tracks + 1)),
            "end before start": dict(tracks=[yt(30, 30), yt(0, 30)]),
            "segment too long": dict(tracks=[yt(0, settings.audio_merge_max_segment_seconds + 1), yt(0, 30)]),
            "total too long": dict(tracks=[yt(0, settings.audio_merge_max_segment_seconds)] *
                                   (settings.audio_merge_max_total_seconds // settings.audio_merge_max_segment_seconds + 1)),
            "bad url": dict(tracks=[{"source": "youtube", "url": "https://evil.com/x", "start_time": 0, "end_time": 30}, yt(0, 30)]),
            "youtube without url": dict(tracks=[{"source": "youtube", "start_time": 0, "end_time": 30}, yt(0, 30)]),
            "upload without file": dict(tracks=[{"source": "upload", "start_time": 0, "end_time": 30}, yt(0, 30)]),
            "file used twice": dict(tracks=[up(0, 0, 30), up(0, 40, 70)]),
            "crossfade longer than half a track": dict(tracks=[yt(0, 30), yt(0, 5)], crossfade_seconds=3),
            "bad format": dict(tracks=[yt(0, 30), yt(0, 30)], output_format="wav"),
            "float time": dict(tracks=[yt(0.5, 30), yt(0, 30)]),
        }
        for name, body in cases.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                AudioMergeRequest(**body)


class UploadTests(unittest.TestCase):
    def test_extension_whitelist(self):
        self.assertEqual(upload_extension("Song.MP3"), ".mp3")
        for name in ("evil.exe", "noext", None, "a.mp3.sh"):
            with self.assertRaises(HTTPException):
                upload_extension(name)


class CommandTests(unittest.TestCase):
    def test_concat_command(self):
        args = build_merge_command("ffmpeg", [("a.webm", 0, 100), ("b.mp3", 60, 75)], "out.mp3", "mp3", 0)
        graph = args[args.index("-filter_complex") + 1]
        self.assertIn("[a0][a1]concat=n=2:v=0:a=1[out]", graph)
        self.assertEqual(args.count("-i"), 2)
        self.assertEqual(args[args.index("-ss") + 1], "60")      # only the upload is seeked
        self.assertEqual(args.count("-ss"), 1)
        self.assertIn("libmp3lame", args)

    def test_crossfade_chain_and_m4a(self):
        args = build_merge_command("ffmpeg", [("a", 0, 30), ("b", 0, 30), ("c", 0, 30)], "out.m4a", "m4a", 2)
        graph = args[args.index("-filter_complex") + 1]
        self.assertIn("[a0][a1]acrossfade=d=2:c1=tri:c2=tri[x1]", graph)
        self.assertIn("[x1][a2]acrossfade=d=2:c1=tri:c2=tri[out]", graph)
        self.assertIn("aac", args)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
class FfmpegTests(unittest.TestCase):
    def tone(self, directory, name, frequency, seconds, channels=2):
        path = Path(directory) / name
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency={frequency}:duration={seconds}", "-ac", str(channels), str(path)], check=True)
        return path

    def duration(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                              "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
        return float(out.stdout)

    def test_joins_trimmed_uploads_in_both_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.tone(directory, "a.wav", 440, 10)
            second = self.tone(directory, "b.wav", 880, 8, channels=1)
            tracks = [{"source": "upload", "start_time": 2, "end_time": 7},    # 5s
                      {"source": "upload", "start_time": 0, "end_time": 4}]    # 4s
            for fmt in ("mp3", "m4a"):
                with self.subTest(fmt):
                    out = merge_audio(tracks, {0: first, 1: second}, fmt, 0, directory)
                    self.assertAlmostEqual(self.duration(out), 9, delta=0.3)
            out = merge_audio(tracks, {0: first, 1: second}, "mp3", 1, directory)
            self.assertAlmostEqual(self.duration(out), 8, delta=0.3)   # crossfade overlaps by 1s

    def test_range_past_the_end_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.tone(directory, "a.wav", 440, 10)
            second = self.tone(directory, "b.wav", 880, 8)
            tracks = [{"source": "upload", "start_time": 0, "end_time": 5},
                      {"source": "upload", "start_time": 4, "end_time": 30}]
            with self.assertRaises(MergeError) as caught:
                merge_audio(tracks, {0: first, 1: second}, "mp3", 0, directory)
            self.assertEqual(caught.exception.code, "INVALID_RANGE")

    def test_invalid_audio_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.mp3"
            bad.write_bytes(b"not audio at all")
            good = self.tone(directory, "a.wav", 440, 10)
            tracks = [{"source": "upload", "start_time": 0, "end_time": 5},
                      {"source": "upload", "start_time": 0, "end_time": 5}]
            with self.assertRaises(MergeError) as caught:
                merge_audio(tracks, {0: bad, 1: good}, "mp3", 0, directory)
            self.assertEqual(caught.exception.code, "INVALID_AUDIO")


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self, reserve=None):
        db = Mock(add=Mock(), commit=AsyncMock(), rollback=AsyncMock(), refresh=AsyncMock())
        credits = Mock(summary=AsyncMock(return_value=SimpleNamespace(is_paid=False)),
                       reserve=reserve or AsyncMock())
        return AudioMergeService(db), db, credits

    async def test_create_reserves_cost_uploads_files_and_commits(self):
        service, db, credits = self.make_service()
        owner = CreditOwner(user_id=uuid.uuid4())
        payload = AudioMergeRequest(tracks=[yt(0, 100), up(0, 0, 75)])
        with patch("app.services.audio_merge_service.CreditService", return_value=credits) as cs, \
             patch("app.services.audio_merge_service.audio_merge_storage") as storage:
            storage.upload_bytes = AsyncMock()
            job = await service.create(payload, [(".mp3", b"data")], owner)
        self.assertFalse(cs.call_args.kwargs["commit"])
        kwargs = credits.reserve.call_args.kwargs
        self.assertEqual(kwargs["amount"], 4)
        self.assertEqual(kwargs["source_type"], "audio_merge")
        self.assertEqual(kwargs["idempotency_key"], audio_merge_reservation_key(job.id, job.attempt_id))
        self.assertEqual(job.credit_cost, 4)
        self.assertEqual(job.total_seconds, 175)
        self.assertEqual(job.tracks[1]["object_name"], f"audiomerge/{job.id}/in-0.mp3")
        storage.upload_bytes.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_insufficient_credits_uploads_nothing(self):
        service, db, credits = self.make_service(AsyncMock(side_effect=InsufficientCreditsError(4, 1)))
        payload = AudioMergeRequest(tracks=[yt(0, 100), up(0, 0, 75)])
        with patch("app.services.audio_merge_service.CreditService", return_value=credits), \
             patch("app.services.audio_merge_service.audio_merge_storage") as storage:
            storage.upload_bytes = AsyncMock()
            with self.assertRaises(InsufficientCreditsError):
                await service.create(payload, [(".mp3", b"data")], CreditOwner(guest_key="g"))
        storage.upload_bytes.assert_not_awaited()
        db.rollback.assert_awaited()
        db.commit.assert_not_awaited()

    async def test_failed_upload_rolls_back_and_cleans_up(self):
        service, db, credits = self.make_service()
        payload = AudioMergeRequest(tracks=[up(0, 0, 30), up(1, 0, 30)])
        with patch("app.services.audio_merge_service.CreditService", return_value=credits), \
             patch("app.services.audio_merge_service.audio_merge_storage") as storage:
            storage.upload_bytes = AsyncMock(side_effect=[None, RuntimeError("gcs down")])
            storage.delete = AsyncMock()
            with self.assertRaises(RuntimeError):
                await service.create(payload, [(".mp3", b"a"), (".wav", b"b")], CreditOwner(user_id=uuid.uuid4()))
        db.commit.assert_not_awaited()
        storage.delete.assert_awaited_once()

    async def test_file_count_must_match_upload_tracks(self):
        service, _, _ = self.make_service()
        payload = AudioMergeRequest(tracks=[yt(0, 30), up(0, 0, 30)])
        for uploads in ([], [(".mp3", b"a"), (".mp3", b"b")]):
            with self.assertRaises(HTTPException):
                await service.create(payload, uploads, CreditOwner(user_id=uuid.uuid4()))

    def test_response_hides_storage_names(self):
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        job = SimpleNamespace(id=uuid.uuid4(), status="queued", error_code=None, output_format="mp3",
                              crossfade_seconds=0, total_seconds=60, credit_cost=2, created_at=now, expires_at=now,
                              tracks=[{"source": "upload", "object_name": "audiomerge/x/in-0.mp3",
                                       "start_time": 0, "end_time": 30}])
        self.assertNotIn("audiomerge", AudioMergeResponse.from_job(job).model_dump_json())


if __name__ == "__main__":
    unittest.main()
