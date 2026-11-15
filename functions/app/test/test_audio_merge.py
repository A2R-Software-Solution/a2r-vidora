"""Offline Song Merger checks: no cloud uploads, YouTube requests or production DB writes."""
import shutil
import subprocess
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
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
        # Millisecond lengths follow the same rule: every started minute counts.
        self.assertEqual(audio_merge_credit_cost([59.999, 0.001]), 1 + 1)
        self.assertEqual(audio_merge_credit_cost([60, 0.001]), 2 + 1)
        self.assertEqual(audio_merge_credit_cost([20.1, 20.2, 19.7]), 1 + 2)     # sums to 60 despite float noise

    def test_rejects_empty_segments(self):
        for bad in ([], [0, 30], [-5, 30]):
            with self.assertRaises(ValueError):
                audio_merge_credit_cost(bad)


class SchemaTests(unittest.TestCase):
    def test_valid_request(self):
        request = AudioMergeRequest(tracks=[yt(60, 160), up(0, 0, 75)], crossfade_seconds=2)
        self.assertEqual([t.seconds for t in request.tracks], [100, 75])

    def test_pro_editor_fields(self):
        source_id = uuid.uuid4()
        request = AudioMergeRequest(tracks=[
            {**yt(0, 30), "volume": 60, "fade_in": 2, "fade_out": 3, "source_id": str(source_id)},
            up(0, 0, 30), up(0, 40, 70)])                     # two sections of one uploaded file
        first, second, _ = request.tracks
        self.assertEqual((first.volume, first.fade_in, first.fade_out, first.source_id), (60, 2, 3, source_id))
        self.assertEqual((second.volume, second.fade_in, second.fade_out, second.source_id), (100, 0, 0, None))

    def test_times_may_be_whole_seconds_or_milliseconds(self):
        request = AudioMergeRequest(tracks=[yt(60, 160), yt(83.4567, 120.5), yt(0.1, 0.3)])
        whole, precise, tiny = request.tracks
        self.assertEqual((whole.start_time, whole.end_time, whole.seconds), (60, 160, 100))
        self.assertEqual((precise.start_time, precise.end_time, precise.seconds), (83.457, 120.5, 37.043))
        self.assertEqual(tiny.seconds, 0.2)                                   # no float noise (0.19999...)

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
            "fades longer than the track": dict(tracks=[{**yt(0, 10), "fade_in": 6, "fade_out": 5}, yt(0, 30)]),
            "volume above 100": dict(tracks=[{**yt(0, 30), "volume": 101}, yt(0, 30)]),
            "fade too long": dict(tracks=[{**yt(0, 30), "fade_in": 11}, yt(0, 30)]),
            "loaded song on an upload": dict(tracks=[{**up(0, 0, 30), "source_id": str(uuid.uuid4())}, yt(0, 30)]),
            "crossfade longer than half a track": dict(tracks=[yt(0, 30), yt(0, 5)], crossfade_seconds=3),
            "bad format": dict(tracks=[yt(0, 30), yt(0, 30)], output_format="wav"),
            "time as text": dict(tracks=[yt("5", 30), yt(0, 30)]),
            "shorter than a tenth of a second": dict(tracks=[yt(10, 10.05), yt(0, 30)]),
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


    def test_millisecond_times_reach_ffmpeg_exactly(self):
        args = build_merge_command("ffmpeg", [("a", 83.457, 37.043, 100, 0, 3), ("b", 0, 0.2)], "out.mp3", "mp3", 0)
        self.assertEqual([args[i + 1] for i, arg in enumerate(args) if arg in ("-ss", "-t")], ["83.457", "37.043", "0.2"])
        self.assertIn("afade=t=out:st=34.043:d=3", args[args.index("-filter_complex") + 1])

    def test_volume_and_fades_are_applied_per_section(self):
        args = build_merge_command("ffmpeg", [("a", 0, 30, 60, 2, 3), ("b", 5, 20, 100, 0, 0)], "out.mp3", "mp3", 0)
        graph = args[args.index("-filter_complex") + 1]
        self.assertIn("[0:a:0]aresample=44100,aformat=channel_layouts=stereo,volume=0.6,"
                      "afade=t=in:st=0:d=2,afade=t=out:st=27:d=3[a0]", graph)
        self.assertIn("[1:a:0]aresample=44100,aformat=channel_layouts=stereo[a1]", graph)   # untouched section


class PeakTests(unittest.TestCase):
    def test_peaks_are_the_loudest_sample_of_each_slice_scaled_to_100(self):
        from array import array
        from app.pipeline.audio_source import peaks_from_samples
        samples = array("h", [0, 100, -200, 50, 0, 0, 400, -100])
        self.assertEqual(peaks_from_samples(samples, 4), [25, 50, 0, 100])
        self.assertEqual(peaks_from_samples(samples, 100), [0, 25, 50, 12, 0, 0, 100, 25])   # never more slices than samples
        self.assertEqual(peaks_from_samples(array("h"), 4), [])
        self.assertEqual(peaks_from_samples(array("h", [0, 0]), 2), [0, 0])                   # silence does not divide by zero

    def test_longer_songs_get_more_waveform_detail_within_bounds(self):
        from app.pipeline.audio_source import peak_count
        self.assertEqual([peak_count(seconds) for seconds in (3, 16, 240, 900, 5000)], [800, 800, 12000, 45000, 45000])


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

    def loudness(self, path, start, length):
        out = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(start), "-t", str(length), "-i", str(path),
                              "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, check=True)
        return float(out.stderr.split("mean_volume:")[1].split("dB")[0])

    def test_two_sections_of_one_file_with_volume_and_fades(self):
        with tempfile.TemporaryDirectory() as directory:
            song = self.tone(directory, "a.wav", 440, 20)
            tracks = [{"source": "upload", "start_time": 0, "end_time": 6, "fade_out": 4},
                      {"source": "upload", "start_time": 10, "end_time": 16, "volume": 25},
                      {"source": "upload", "start_time": 4, "end_time": 8}]
            out = merge_audio(tracks, {0: song, 1: song, 2: song}, "mp3", 0, directory)
            self.assertAlmostEqual(self.duration(out), 16, delta=0.3)
            full = self.loudness(out, 12.5, 3)                       # third section, untouched
            self.assertAlmostEqual(self.loudness(out, 0, 1.5), full, delta=1)        # before the fade
            self.assertLess(self.loudness(out, 4.5, 1.4), full - 6)                  # end of the fade-out
            self.assertAlmostEqual(self.loudness(out, 7, 4), full - 12, delta=1.5)   # 25% is about -12 dB

    def test_cuts_are_exact_to_a_fraction_of_a_second(self):
        with tempfile.TemporaryDirectory() as directory:
            song = self.tone(directory, "a.wav", 440, 20)
            tracks = [{"source": "upload", "start_time": 2.25, "end_time": 4.595},     # 2.345s
                      {"source": "upload", "start_time": 10.5, "end_time": 11.611}]    # 1.111s
            out = merge_audio(tracks, {0: song, 1: song}, "m4a", 0, directory)
            self.assertAlmostEqual(self.duration(out), 3.456, delta=0.08)

    def test_youtube_section_is_downloaded_in_whole_seconds_then_cut_precisely(self):
        with tempfile.TemporaryDirectory() as directory:
            section = self.tone(directory, "yt0.wav", 440, 6)                      # stands for seconds 83-89 of the video
            other = self.tone(directory, "b.wav", 880, 5)
            tracks = [{"source": "youtube", "url": URL, "start_time": 83.4, "end_time": 88.15},   # 4.75s
                      {"source": "upload", "start_time": 0, "end_time": 2}]
            with patch("app.pipeline.audio_merger.fetch_youtube_section", return_value=section) as fetch, \
                 patch("app.pipeline.audio_merger.secret_manager_client") as secrets:
                secrets.get_youtube_cookie.return_value = ("secret", "cookies")
                out = merge_audio(tracks, {1: other}, "m4a", 0, directory)
            self.assertEqual(fetch.call_args.args[1:3], (83, 89))
            self.assertAlmostEqual(self.duration(out), 6.75, delta=0.08)

    def test_stored_youtube_audio_is_used_instead_of_a_download(self):
        with tempfile.TemporaryDirectory() as directory:
            song = self.tone(directory, "a.wav", 440, 20)
            tracks = [{"source": "youtube", "url": URL, "start_time": 2, "end_time": 7},
                      {"source": "youtube", "url": URL, "start_time": 10, "end_time": 14}]
            with patch("app.pipeline.audio_merger.fetch_youtube_section") as fetch, \
                 patch("app.pipeline.audio_merger.secret_manager_client") as secrets:
                out = merge_audio(tracks, {0: song, 1: song}, "mp3", 0, directory)
            fetch.assert_not_called()
            secrets.get_youtube_cookie.assert_not_called()
            self.assertAlmostEqual(self.duration(out), 9, delta=0.3)

    def test_browser_recording_without_a_stored_length_can_be_merged(self):
        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory) / "mic.webm"
            # "-live 1" writes WebM the way MediaRecorder does: no duration, no seek index.
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
                            "-c:a", "libopus", "-f", "webm", "-live", "1", str(recording)], check=True)
            tracks = [{"source": "upload", "start_time": 1, "end_time": 6},
                      {"source": "upload", "start_time": 7, "end_time": 11}]
            out = merge_audio(tracks, {0: recording, 1: recording}, "mp3", 0, directory)
            self.assertAlmostEqual(self.duration(out), 9, delta=0.3)

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

    async def test_sections_of_one_file_store_it_once_and_keep_their_effects(self):
        service, db, credits = self.make_service()
        payload = AudioMergeRequest(tracks=[{**up(0, 0, 30), "volume": 70, "fade_in": 2}, up(0, 40, 70)])
        with patch("app.services.audio_merge_service.CreditService", return_value=credits), \
             patch("app.services.audio_merge_service.audio_merge_storage") as storage:
            storage.upload_bytes = AsyncMock()
            job = await service.create(payload, [(".mp3", b"data")], CreditOwner(user_id=uuid.uuid4()))
        storage.upload_bytes.assert_awaited_once()
        self.assertEqual(job.tracks[0]["object_name"], job.tracks[1]["object_name"])
        self.assertEqual([(t["volume"], t["fade_in"], t["fade_out"]) for t in job.tracks], [(70, 2, 0), (100, 0, 0)])
        self.assertEqual(credits.reserve.call_args.kwargs["amount"], 1 + 1)      # same price rule as Simple mode

    async def test_millisecond_tracks_are_stored_exactly_and_priced_by_started_minutes(self):
        service, db, credits = self.make_service()
        payload = AudioMergeRequest(tracks=[yt(10.25, 40.75), yt(100, 130.001)])   # 30.5s + 30.001s = 60.501s
        with patch("app.services.audio_merge_service.CreditService", return_value=credits), \
             patch("app.services.audio_merge_service.audio_merge_storage"):
            job = await service.create(payload, [], CreditOwner(user_id=uuid.uuid4()))
        self.assertEqual([(t["start_time"], t["end_time"]) for t in job.tracks], [(10.25, 40.75), (100, 130.001)])
        self.assertEqual((job.total_seconds, job.credit_cost), (61, 2 + 1))

    async def test_loaded_song_audio_is_attached_only_when_it_is_the_owners_and_ready(self):
        service, db, credits = self.make_service()
        known, unknown = uuid.uuid4(), uuid.uuid4()
        payload = AudioMergeRequest(tracks=[{**yt(0, 30), "source_id": str(known)},
                                            {**yt(40, 70), "source_id": str(unknown)}])
        sources = Mock(originals=AsyncMock(return_value={known: "audiomerge/sources/x/original.webm"}))
        with patch("app.services.audio_merge_service.CreditService", return_value=credits), \
             patch("app.services.audio_merge_service.AudioSourceService", return_value=sources), \
             patch("app.services.audio_merge_service.audio_merge_storage"):
            owner = CreditOwner(user_id=uuid.uuid4())
            job = await service.create(payload, [], owner)
        sources.originals.assert_awaited_once_with({known: "dQw4w9WgXcQ", unknown: "dQw4w9WgXcQ"}, owner)
        self.assertEqual(job.tracks[0]["source_object"], "audiomerge/sources/x/original.webm")
        self.assertNotIn("source_object", job.tracks[1])                          # falls back to YouTube
        self.assertNotIn("audiomerge", AudioMergeResponse.from_job(SimpleNamespace(
            id=job.id, status="queued", error_code=None, output_format="mp3", crossfade_seconds=0, total_seconds=60,
            credit_cost=2, created_at=job.created_at, expires_at=job.expires_at, tracks=job.tracks)).model_dump_json())

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


class SourceServiceTests(unittest.IsolatedAsyncioTestCase):
    """Loading a song in the Pro editor is free, so it is limited per owner."""
    def source(self, **fields):
        now = datetime.now(timezone.utc)
        values = dict(id=uuid.uuid4(), video_id="dQw4w9WgXcQ", url=URL, status="ready", error_code=None, title="Song",
                      duration_seconds=200, peaks=[1, 2], preview_object="audiomerge/sources/x/preview.mp3",
                      original_object="audiomerge/sources/x/original.webm", created_at=now, updated_at=now,
                      expires_at=now + timedelta(hours=2))
        return SimpleNamespace(**{**values, **fields})

    def service(self, rows):
        from app.services.audio_source_service import AudioSourceService
        result = Mock(scalars=Mock(return_value=rows), scalar_one_or_none=Mock(return_value=rows[0] if rows else None))
        db = Mock(add=Mock(), commit=AsyncMock(), execute=AsyncMock(return_value=result))
        return AudioSourceService(db), db

    async def test_a_song_already_loaded_is_reused(self):
        existing = self.source()
        service, db = self.service([existing])
        source, created = await service.create(URL, CreditOwner(user_id=uuid.uuid4()))
        self.assertEqual((source, created), (existing, False))
        db.add.assert_not_called()

    async def test_failed_or_nearly_expired_songs_are_loaded_again(self):
        soon = datetime.now(timezone.utc) + timedelta(minutes=5)
        for stale in (self.source(status="failed"), self.source(expires_at=soon)):
            service, db = self.service([stale])
            owner = CreditOwner(guest_key="g")
            source, created = await service.create(URL, owner)
            self.assertTrue(created)
            self.assertEqual((source.status, source.video_id, source.guest_key), ("queued", "dQw4w9WgXcQ", "g"))
            db.add.assert_called_once_with(source)

    async def test_hourly_limit_stops_new_songs_but_not_reuse(self):
        other = [self.source(video_id=f"video{i:06d}") for i in range(settings.audio_merge_sources_per_hour)]
        service, db = self.service(other)
        with self.assertRaises(HTTPException) as caught:
            await service.create(URL, CreditOwner(user_id=uuid.uuid4()))
        self.assertEqual(caught.exception.status_code, 429)
        db.add.assert_not_called()
        service, _ = self.service(other + [self.source()])
        self.assertFalse((await service.create(URL, CreditOwner(user_id=uuid.uuid4())))[1])

    async def test_stalled_song_is_reported_failed(self):
        from app.pipeline.audio_source_worker import stall_window
        old = datetime.now(timezone.utc) - stall_window() - timedelta(seconds=5)
        stuck = self.source(status="processing", updated_at=old)
        service, _ = self.service([stuck])
        source = await service.get(stuck.id, CreditOwner(user_id=uuid.uuid4()))
        self.assertEqual((source.status, source.error_code), ("failed", "TIMED_OUT"))

    async def test_description_signs_the_preview_and_hides_storage_names(self):
        service, _ = self.service([])
        with patch("app.services.audio_source_service.audio_merge_storage") as storage:
            storage.signed_preview_url = AsyncMock(return_value="https://signed.example/preview")
            ready = await service.describe(self.source())
            pending = await service.describe(self.source(status="processing", peaks=None, preview_object=None))
        self.assertEqual((ready["preview_url"], ready["peaks"]), ("https://signed.example/preview", [1, 2]))
        self.assertNotIn("audiomerge", str(ready))
        self.assertEqual((pending["preview_url"], pending["peaks"]), (None, None))
        storage.signed_preview_url.assert_awaited_once()


class SourceApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from app.core.rate_limit import limiter
        from app.deps import get_current_user_id, get_db
        from app.main import app
        from app.routes import audio_merge_routes
        limiter.reset()
        self.addCleanup(limiter.reset)

        async def nobody():
            return None

        async def db():
            yield Mock()
        app.dependency_overrides[get_current_user_id] = nobody
        app.dependency_overrides[get_db] = db
        self.addCleanup(app.dependency_overrides.clear)
        now = datetime.now(timezone.utc)
        self.row = SimpleNamespace(id=uuid.uuid4())
        self.described = {"id": self.row.id, "video_id": "dQw4w9WgXcQ", "url": URL, "title": None, "status": "queued",
                          "error_code": None, "duration_seconds": None, "peaks": None, "preview_url": None,
                          "expires_at": now}
        self.sources = Mock(create=AsyncMock(return_value=(self.row, True)), get=AsyncMock(return_value=self.row),
                            describe=AsyncMock(return_value=self.described), mark_failed=AsyncMock())
        self.queue = Mock()
        for target, name, value in ((audio_merge_routes, "AudioSourceService", Mock(return_value=self.sources)),
                                    (audio_merge_routes.admin_functions, "task_queue", Mock(return_value=self.queue)),
                                    (settings, "audio_merge_enabled", True), (settings, "audio_merge_bucket", "bucket"),
                                    (settings, "audio_merge_sources_inline", False)):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_new_song_is_queued_once_and_costs_nothing(self):
        response = self.client.post("/audio-merges/sources", json={"url": URL})
        self.assertEqual((response.status_code, response.json()["status"]), (202, "queued"))
        payload = self.queue.enqueue.call_args.args[0]
        self.assertEqual(payload, {"data": {"source_id": str(self.row.id)}})

    def test_reused_song_is_not_queued_again(self):
        self.sources.create.return_value = (self.row, False)
        self.assertEqual(self.client.post("/audio-merges/sources", json={"url": URL}).status_code, 202)
        self.queue.enqueue.assert_not_called()

    def test_queue_failure_marks_the_song_failed(self):
        self.queue.enqueue.side_effect = RuntimeError("tasks down")
        self.assertEqual(self.client.post("/audio-merges/sources", json={"url": URL}).status_code, 503)
        self.sources.mark_failed.assert_awaited_once_with(self.row, "QUEUE_UNAVAILABLE")

    def test_only_youtube_links_are_accepted(self):
        self.assertEqual(self.client.post("/audio-merges/sources", json={"url": "https://evil.com/x"}).status_code, 422)
        self.sources.create.assert_not_awaited()

    def test_status_is_read_by_id_and_limits_advertise_the_editor(self):
        self.assertEqual(self.client.get(f"/audio-merges/sources/{self.row.id}").status_code, 200)
        limits = self.client.get("/audio-merges/limits").json()
        self.assertTrue(limits["pro_enabled"])
        self.assertEqual(limits["max_fade_seconds"], 10)


if __name__ == "__main__":
    unittest.main()
