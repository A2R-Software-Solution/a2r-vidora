"""Offline Shorts checks: no cloud uploads, YouTube requests or production DB writes."""
import json
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
from app.schemas.short_schema import ShortRequest
from app.services.short_service import ShortService
from app.pipeline.short_renderer import caption_text, render_local


class ShortsTests(unittest.IsolatedAsyncioTestCase):
    def test_invalid_ranges(self):
        for start, end in [(-1, 30), (0, 19), (0, 61), (50, 20), (0.5, 30)]:
            with self.assertRaises(ValidationError):
                ShortRequest(start_time=start, end_time=end)

    async def test_duplicate_does_not_reserve_or_enqueue_again(self):
        job = SimpleNamespace(start_time=0, end_time=30, status="completed", updated_at=datetime.now(timezone.utc))
        db = Mock(commit=AsyncMock(), execute=AsyncMock(side_effect=[Mock(), Mock(scalars=Mock(return_value=[job]))]))
        service = ShortService(db)
        service._video = AsyncMock(return_value=SimpleNamespace(duration=100))
        with patch("app.services.short_service.VideoService") as videos, patch("app.services.short_service.TranscriptChunkRepository") as chunks:
            chunks.return_value.find_in_time_range = AsyncMock(return_value=[SimpleNamespace(chunk_text="hello")])
            result, created = await service.create(uuid.uuid4(), ShortRequest(start_time=0, end_time=30), None)
        self.assertIs(result, job)
        self.assertFalse(created)

    async def test_two_reservations_reject_third(self):
        jobs = [SimpleNamespace(start_time=0, end_time=30, status=state, updated_at=datetime.now(timezone.utc)) for state in ["queued", "completed"]]
        db = Mock(execute=AsyncMock(side_effect=[Mock(), Mock(scalars=Mock(return_value=jobs))]))
        service = ShortService(db)
        service._video = AsyncMock(return_value=SimpleNamespace(duration=100))
        with patch("app.services.short_service.VideoService"), patch("app.services.short_service.TranscriptChunkRepository") as chunks:
            chunks.return_value.find_in_time_range = AsyncMock(return_value=[SimpleNamespace(chunk_text="hello")])
            with self.assertRaises(HTTPException) as error:
                await service.create(uuid.uuid4(), ShortRequest(start_time=40, end_time=70), None)
        self.assertEqual(error.exception.status_code, 409)

    def test_stalled_jobs_release_slot(self):
        job = SimpleNamespace(status="rendering", updated_at=datetime.now(timezone.utc) - timedelta(hours=2))
        ShortService._expire_stalled([job])
        self.assertEqual(job.status, "failed")

    async def test_failed_range_retries_with_new_attempt(self):
        old_attempt = uuid.uuid4()
        job = SimpleNamespace(start_time=0, end_time=30, status="failed", attempt_id=old_attempt,
                              updated_at=datetime.now(timezone.utc))
        db = Mock(commit=AsyncMock(), refresh=AsyncMock(), execute=AsyncMock(side_effect=[Mock(), Mock(scalars=Mock(return_value=[job]))]))
        service = ShortService(db)
        service._video = AsyncMock(return_value=SimpleNamespace(duration=100, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        with patch("app.services.short_service.VideoService"), patch("app.services.short_service.TranscriptChunkRepository") as chunks:
            chunks.return_value.find_in_time_range = AsyncMock(return_value=[SimpleNamespace(chunk_text="hello")])
            result, created = await service.create(uuid.uuid4(), ShortRequest(start_time=0, end_time=30), None)
        self.assertTrue(created)
        self.assertEqual(result.status, "queued")
        self.assertNotEqual(result.attempt_id, old_attempt)

    async def test_access_denial_happens_before_listing(self):
        from app.services.video_service import VideoAccessDeniedError
        db = Mock(execute=AsyncMock())
        service = ShortService(db)
        service._video = AsyncMock(side_effect=VideoAccessDeniedError())
        with self.assertRaises(VideoAccessDeniedError):
            await service.list(uuid.uuid4(), uuid.uuid4())
        db.execute.assert_not_awaited()

    async def test_expired_download_never_signs(self):
        service = ShortService(Mock())
        service.get = AsyncMock(return_value=SimpleNamespace(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1), status="completed"))
        with patch("app.services.short_service.short_storage.signed_url", new_callable=AsyncMock) as sign:
            with self.assertRaises(HTTPException) as error:
                await service.download(uuid.uuid4(), uuid.uuid4(), None, True)
            self.assertEqual(error.exception.status_code, 410)
            sign.assert_not_awaited()

    def test_captions_are_clipped_and_strip_control_text(self):
        chunk = SimpleNamespace(start_time=5, end_time=40, chunk_text="<tag> hello {style} world " * 10)
        text = caption_text([chunk], 10, 30)
        self.assertIn("00:00:00,000", text)
        self.assertNotIn("<", text)
        self.assertNotIn("{", text)
        import re
        times = re.findall(r" --> (\d\d:\d\d:\d\d,\d\d\d)", text)
        self.assertTrue(times)
        self.assertLessEqual(max(times), "00:00:20,000")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires FFmpeg and ffprobe")
    def test_real_vertical_mp4_render(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15",
                            "-f", "lavfi", "-i", "sine=frequency=440", "-t", "2", "-c:v", "libx264", "-c:a", "aac", str(source)], check=True)
            (Path(directory) / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nCaption test\n", encoding="utf-8")
            output = render_local(source, 2, directory)
            result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)], capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            video = next(s for s in info["streams"] if s["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"]), (720, 1280))
            self.assertEqual(video["codec_name"], "h264")
            self.assertTrue(any(s["codec_type"] == "audio" for s in info["streams"]))
            self.assertAlmostEqual(float(info["format"]["duration"]), 2, delta=.2)
