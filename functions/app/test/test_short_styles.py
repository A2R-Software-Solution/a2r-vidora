"""Styled Shorts: options validation, ASS captions, filter graph, presets and routes. All offline."""
import json
import shutil
import subprocess
import tempfile
import typing
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import settings
from app.core.rate_limit import limiter
from app.deps import get_current_user_id, get_db
from app.main import app
from app.pipeline import short_catalog
from app.pipeline.short_ass import build_ass
from app.pipeline.short_renderer import build_filter, prepare_captions, render_local
from app.routes import short_preset_routes, short_routes
from app.schemas import short_schema
from app.schemas.short_schema import ShortOptions, ShortPresetRequest, ShortRange, ShortRequest, ShortStyle
from app.services.short_preset_service import MAX_PRESETS, ShortPresetService
from app.services.short_service import ShortService

CUES = [{"start": 0.0, "end": 2.0, "text": "Then Krishna said"}, {"start": 2.0, "end": 4.0, "text": "do your duty"}]


def request(**extra):
    return ShortRequest(start_time=0, end_time=30, **extra)


class CatalogTests(unittest.TestCase):
    def test_schema_literals_match_the_catalog(self):
        self.assertEqual(set(typing.get_args(short_schema.FontKey)), set(short_catalog.FONTS))
        self.assertEqual(set(typing.get_args(short_schema.Ratio)), set(short_catalog.RATIOS))
        self.assertEqual(set(typing.get_args(short_schema.Background)), set(short_catalog.BACKGROUNDS))
        self.assertEqual(set(typing.get_args(short_schema.Position)), set(short_catalog.POSITIONS))

    def test_every_font_is_bundled_with_its_licence(self):
        licences = " ".join(p.name for p in short_catalog.FONT_DIR.glob("OFL-*.txt"))
        for key, font in short_catalog.FONTS.items():
            with self.subTest(font=key):
                self.assertTrue(short_catalog.font_file(key).is_file())
                self.assertIn(font["family"].split()[0], licences)

    def test_builtin_presets_are_valid_styles(self):
        for key, preset in short_catalog.PRESETS.items():
            with self.subTest(preset=key):
                ShortStyle(**preset["style"])


class OptionsTests(unittest.TestCase):
    def test_defaults_are_stored_as_nothing_and_hash_empty(self):
        self.assertIsNone(request().options_dict())
        self.assertEqual(request().options_hash(), "")

    def test_a_different_look_has_its_own_stable_hash(self):
        a, b = request(ratio="1:1"), request(ratio="1:1")
        self.assertEqual(a.options_hash(), b.options_hash())
        self.assertEqual(len(a.options_hash()), 64)
        self.assertNotEqual(a.options_hash(), request(ratio="4:5").options_hash())
        self.assertNotEqual(a.options_hash(), request(style={"color": "#FF0000"}).options_hash())

    def test_bad_values_are_rejected(self):
        bad = [{"ratio": "2:1"}, {"background": "plaid"}, {"style": {"font": "comic_sans"}},
               {"style": {"size": 500}}, {"style": {"size": 5}}, {"style": {"color": "red"}},
               {"style": {"color": "#12345"}}, {"style": {"outline_width": 99}},
               {"style": {"position": "left"}}, {"style": {"shell": "rm -rf"}}, {"extra": 1},
               {"background_color": "url(x)"}]
        for extra in bad:
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                request(**extra)

    def test_old_requests_without_options_still_work(self):
        self.assertEqual(ShortRequest(start_time=10, end_time=40).ratio, "9:16")
        with self.assertRaises(ValidationError):
            ShortRange(start_time=0, end_time=10)


class CaptionValidationTests(unittest.TestCase):
    def test_valid_captions_are_accepted(self):
        self.assertEqual(len(request(captions=[{"start": 0, "end": 2, "text": "Hi"},
                                               {"start": 2, "end": 30, "text": "There"}]).captions), 2)

    def test_markup_and_control_characters_are_removed(self):
        text = request(captions=[{"start": 0, "end": 2, "text": "a {\\b1}b\\N<i>c</i>\x00"}]).captions[0].text
        for char in "{}\\<>\x00":
            self.assertNotIn(char, text)

    def test_bad_captions_are_rejected(self):
        cases = {
            "empty list": [],
            "overlap": [{"start": 0, "end": 5, "text": "a"}, {"start": 4, "end": 8, "text": "b"}],
            "out of order": [{"start": 5, "end": 8, "text": "a"}, {"start": 0, "end": 2, "text": "b"}],
            "past the clip": [{"start": 0, "end": 31, "text": "a"}],
            "ends before start": [{"start": 5, "end": 5, "text": "a"}],
            "blank after cleaning": [{"start": 0, "end": 2, "text": "{} \\"}],
            "too long": [{"start": 0, "end": 2, "text": "x" * 121}],
            "negative": [{"start": -1, "end": 2, "text": "a"}],
            "too many": [{"start": i * 0.4, "end": i * 0.4 + 0.3, "text": "a"} for i in range(61)],
        }
        for name, captions in cases.items():
            with self.subTest(name), self.assertRaises(ValidationError):
                request(captions=captions)

    def test_total_caption_text_is_capped(self):
        under = [{"start": i * 0.7, "end": i * 0.7 + 0.6, "text": "x" * 120} for i in range(33)]  # 3960 chars
        self.assertEqual(len(request(captions=under).captions), 33)
        over = [{"start": i * 0.7, "end": i * 0.7 + 0.6, "text": "x" * 120} for i in range(34)]  # 4080 chars
        with self.assertRaises(ValidationError):
            request(captions=over)


class AssTests(unittest.TestCase):
    def build(self, ratio="9:16", **style):
        return build_ass(CUES, ShortStyle(**style).model_dump(), ratio)

    def test_script_matches_the_frame(self):
        ass = self.build("16:9")
        self.assertIn("PlayResX: 1280", ass)
        self.assertIn("PlayResY: 720", ass)
        self.assertEqual(ass.count("Dialogue:"), 2)

    def test_colours_are_ass_bgr(self):
        ass = self.build(color="#FF8000", outline_color="#0000FF")
        self.assertIn("&H000080FF", ass)  # primary: BGR of FF8000
        self.assertIn("&H00FF0000", ass)  # outline: BGR of 0000FF

    def test_position_sets_alignment(self):
        for position, alignment in {"bottom": "2", "middle": "5", "top": "8"}.items():
            with self.subTest(position):
                style_line = next(l for l in self.build(position=position).splitlines() if l.startswith("Style:"))
                self.assertEqual(style_line.split(",")[18], alignment)

    def test_font_size_scales_with_the_frame(self):
        def size(ratio):
            line = next(l for l in self.build(ratio, size=64).splitlines() if l.startswith("Style:"))
            return int(line.split(",")[2])
        self.assertEqual(size("9:16"), 43)  # 64 * 720 / 1080
        self.assertEqual(size("16:9"), 43)  # smaller side drives it, so landscape is not huge

    def test_box_uses_opaque_box_style_with_opacity(self):
        line = next(l for l in self.build(box=True, box_opacity=50, outline=True).splitlines() if l.startswith("Style:"))
        fields = line.split(",")
        self.assertEqual(fields[15], "3")
        self.assertEqual(fields[5], "&H80000000")

    def test_no_outline_means_zero_width(self):
        line = next(l for l in self.build(outline=False).splitlines() if l.startswith("Style:"))
        self.assertEqual(line.split(",")[16], "0")

    def test_uppercase_and_karaoke(self):
        plain = self.build(uppercase=True)
        self.assertIn("THEN KRISHNA SAID", plain)
        self.assertNotIn("\\k", plain)
        karaoke = self.build(highlight=True, highlight_color="#FFE600")
        self.assertIn("{\\k", karaoke)
        total = sum(int(n) for n in __import__("re").findall(r"\\k(\d+)", karaoke.split("\n")[-3]))
        self.assertAlmostEqual(total, 200, delta=3)  # the first cue lasts 2 s

    def test_cue_text_cannot_inject_ass_overrides(self):
        ass = build_ass([{"start": 0, "end": 2, "text": "ok {\\fs200}\\Nhi"}], ShortStyle().model_dump(), "9:16")
        dialogue = next(l for l in ass.splitlines() if l.startswith("Dialogue:"))
        self.assertNotIn("{", dialogue)
        self.assertNotIn("\\", dialogue)


class FilterTests(unittest.TestCase):
    def options(self, **raw):
        return ShortOptions(**raw).model_dump()

    def test_each_background_builds_its_own_graph(self):
        blur = build_filter(self.options())
        self.assertIn("boxblur", blur)
        self.assertIn("scale=720:1280", blur)
        fill = build_filter(self.options(background="fill"))
        self.assertIn("crop=720:1280", fill)
        self.assertNotIn("boxblur", fill)
        solid = build_filter(self.options(background="solid", background_color="#1a2b6d"))
        self.assertIn("pad=720:1280", solid)
        self.assertIn("0x1A2B6D", solid)

    def test_ratio_sets_the_frame(self):
        self.assertIn("scale=1280:720", build_filter(self.options(ratio="16:9")))
        self.assertIn("scale=720:900", build_filter(self.options(ratio="4:5")))

    def test_graph_always_ends_in_the_output_label_with_captions(self):
        for background in short_catalog.BACKGROUNDS:
            self.assertTrue(build_filter(self.options(background=background)).endswith("ass=captions.ass:fontsdir=fonts[out]"))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires FFmpeg and ffprobe")
class RenderTests(unittest.TestCase):
    def test_every_ratio_and_background_renders_with_every_font(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15",
                            "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-c:v", "libx264",
                            "-c:a", "aac", str(source)], check=True)
            cases = [{"ratio": r} for r in short_catalog.RATIOS]
            cases += [{"background": b} for b in short_catalog.BACKGROUNDS]
            cases += [{"style": {"font": f}} for f in short_catalog.FONTS]
            cases += [{"style": preset["style"]} for preset in short_catalog.PRESETS.values()]
            for index, raw in enumerate(cases):
                with self.subTest(raw=raw):
                    work = Path(tmp) / str(index)
                    work.mkdir()
                    options = ShortOptions(**raw).model_dump()
                    prepare_captions(work, options, CUES)
                    output = render_local(source, 1, work, None, options)
                    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)],
                                                     capture_output=True, text=True, check=True).stdout)
                    video = next(s for s in info["streams"] if s["codec_type"] == "video")
                    self.assertEqual((video["width"], video["height"]), short_catalog.RATIOS[options["ratio"]])


def _service(jobs, duration=100):
    db = Mock(add=Mock(), commit=AsyncMock(), refresh=AsyncMock(),
              execute=AsyncMock(side_effect=[Mock(), Mock(scalars=Mock(return_value=jobs))]))
    service = ShortService(db)
    service._video = AsyncMock(return_value=SimpleNamespace(duration=duration,
                                                            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    return service, db


class StyledCreateTests(unittest.IsolatedAsyncioTestCase):
    async def create(self, service, payload):
        with patch("app.services.short_service.VideoService"), \
             patch("app.services.short_service.TranscriptChunkRepository") as chunks:
            chunks.return_value.find_in_time_range = AsyncMock(return_value=[SimpleNamespace(chunk_text="hello")])
            return await service.create(uuid.uuid4(), payload, None), chunks

    async def test_same_range_in_another_look_is_a_new_render(self):
        default_job = SimpleNamespace(start_time=0, end_time=30, status="completed", options_hash="",
                                      updated_at=datetime.now(timezone.utc))
        service, db = _service([default_job])
        (job, created), _ = await self.create(service, request(ratio="1:1"))
        self.assertTrue(created)
        self.assertIsNot(job, default_job)
        self.assertEqual(job.options["ratio"], "1:1")
        self.assertEqual(job.options_hash, request(ratio="1:1").options_hash())

    async def test_repeating_the_same_look_returns_the_existing_render(self):
        payload = request(ratio="1:1")
        existing = SimpleNamespace(start_time=0, end_time=30, status="queued", options_hash=payload.options_hash(),
                                   updated_at=datetime.now(timezone.utc))
        service, _ = _service([existing])
        (job, created), _ = await self.create(service, payload)
        self.assertIs(job, existing)
        self.assertFalse(created)

    async def test_edited_captions_need_no_transcript_lookup(self):
        service, _ = _service([])
        payload = request(captions=[{"start": 0, "end": 5, "text": "my own words"}])
        (job, created), chunks = await self.create(service, payload)
        self.assertTrue(created)
        chunks.return_value.find_in_time_range.assert_not_awaited()
        self.assertEqual(job.options["captions"][0]["text"], "my own words")

    async def test_default_look_stores_no_options(self):
        service, _ = _service([])
        (job, _), _ = await self.create(service, request())
        self.assertIsNone(job.options)
        self.assertEqual(job.options_hash, "")


class DraftTests(unittest.IsolatedAsyncioTestCase):
    async def draft(self, chunks, duration=100):
        service = ShortService(Mock())
        service._video = AsyncMock(return_value=SimpleNamespace(duration=duration))
        with patch("app.services.short_service.VideoService"), \
             patch("app.services.short_service.TranscriptChunkRepository") as repo:
            repo.return_value.find_in_time_range = AsyncMock(return_value=chunks)
            return await service.draft(uuid.uuid4(), ShortRange(start_time=10, end_time=40), None)

    async def test_returns_cues_relative_to_the_clip(self):
        cues = await self.draft([SimpleNamespace(start_time=8, end_time=20, chunk_text="one two three four five six")])
        self.assertEqual(cues[0]["start"], 0)
        self.assertTrue(all(0 <= c["start"] < c["end"] <= 30 for c in cues))

    async def test_no_transcript_is_a_422(self):
        with self.assertRaises(HTTPException) as error:
            await self.draft([SimpleNamespace(start_time=8, end_time=20, chunk_text="   ")])
        self.assertEqual(error.exception.status_code, 422)

    async def test_clip_past_the_end_is_a_422(self):
        with self.assertRaises(HTTPException) as error:
            await self.draft([], duration=30)
        self.assertEqual(error.exception.status_code, 422)


class PresetServiceTests(unittest.IsolatedAsyncioTestCase):
    def db(self, count=0):
        return Mock(add=Mock(), commit=AsyncMock(), refresh=AsyncMock(), rollback=AsyncMock(),
                    execute=AsyncMock(return_value=Mock(scalar_one=Mock(return_value=count))))

    async def test_saves_a_preset(self):
        db = self.db()
        preset = await ShortPresetService(db).create(uuid.uuid4(), ShortPresetRequest(name="  My  look ", style={}))
        self.assertEqual(preset.name, "My look")
        self.assertEqual(preset.style["font"], "poppins_semibold")
        db.commit.assert_awaited_once()

    async def test_the_limit_is_enforced(self):
        db = self.db(count=MAX_PRESETS)
        with self.assertRaises(HTTPException) as error:
            await ShortPresetService(db).create(uuid.uuid4(), ShortPresetRequest(name="x", style={}))
        self.assertEqual(error.exception.status_code, 409)
        db.add.assert_not_called()

    async def test_a_duplicate_name_is_a_409(self):
        from sqlalchemy.exc import IntegrityError
        db = self.db()
        db.commit = AsyncMock(side_effect=IntegrityError("x", {}, Exception()))
        with self.assertRaises(HTTPException) as error:
            await ShortPresetService(db).create(uuid.uuid4(), ShortPresetRequest(name="x", style={}))
        self.assertEqual(error.exception.status_code, 409)
        db.rollback.assert_awaited_once()

    async def test_deleting_another_users_preset_is_a_404(self):
        db = Mock(delete=AsyncMock(), commit=AsyncMock(),
                  execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None))))
        with self.assertRaises(HTTPException) as error:
            await ShortPresetService(db).delete(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(error.exception.status_code, 404)
        db.delete.assert_not_awaited()

    def test_preset_input_is_validated(self):
        for raw in [{"name": "", "style": {}}, {"name": "x" * 41, "style": {}}, {"name": "{}", "style": {}},
                    {"name": "ok", "style": {"font": "nope"}}, {"name": "ok", "style": {}, "extra": 1}]:
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                ShortPresetRequest(**raw)


class RouteTests(unittest.TestCase):
    def setUp(self):
        limiter.reset()
        self.user = None

        async def user():
            return self.user

        async def db():
            yield None

        app.dependency_overrides[get_current_user_id] = user
        app.dependency_overrides[get_db] = db
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(limiter.reset)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def send(self, method, path, body=None):
        return self.client.request(method, path, json=body, headers={"Origin": settings.cors_origins[0]})

    def test_options_lists_what_the_editor_can_offer(self):
        data = self.send("GET", "/shorts/options").json()
        self.assertEqual([f["key"] for f in data["fonts"]], list(short_catalog.FONTS))
        self.assertEqual({r["key"] for r in data["ratios"]}, set(short_catalog.RATIOS))
        self.assertEqual({p["key"] for p in data["presets"]}, set(short_catalog.PRESETS))
        self.assertEqual(data["limits"]["max_presets"], MAX_PRESETS)

    def test_options_are_rate_limited(self):
        for _ in range(60):
            self.assertEqual(self.send("GET", "/shorts/options").status_code, 200)
        self.assertEqual(self.send("GET", "/shorts/options").status_code, 429)

    def test_presets_need_an_account(self):
        self.assertEqual(self.send("GET", "/shorts/presets").status_code, 401)
        self.assertEqual(self.send("POST", "/shorts/presets", {"name": "x", "style": {}}).status_code, 401)
        self.assertEqual(self.send("DELETE", f"/shorts/presets/{uuid.uuid4()}").status_code, 401)

    def test_preset_writes_are_rate_limited(self):
        self.user = uuid.uuid4()
        now = datetime.now(timezone.utc)
        saved = SimpleNamespace(id=uuid.uuid4(), name="x", style=ShortStyle().model_dump(), created_at=now)
        service = Mock(create=AsyncMock(return_value=saved), delete=AsyncMock(), list=AsyncMock(return_value=[saved]))
        with patch.object(short_preset_routes, "ShortPresetService", return_value=service):
            self.assertEqual(self.send("GET", "/shorts/presets").json()[0]["name"], "x")
            for _ in range(20):
                self.assertEqual(self.send("POST", "/shorts/presets", {"name": "x", "style": {}}).status_code, 201)
            self.assertEqual(self.send("POST", "/shorts/presets", {"name": "x", "style": {}}).status_code, 429)
            self.assertEqual(self.send("DELETE", f"/shorts/presets/{uuid.uuid4()}").status_code, 204)

    def test_invalid_preset_style_is_a_422(self):
        self.user = uuid.uuid4()
        self.assertEqual(self.send("POST", "/shorts/presets", {"name": "x", "style": {"size": 9999}}).status_code, 422)

    def test_draft_validates_the_range_and_is_rate_limited(self):
        self.user = uuid.uuid4()
        video_id = uuid.uuid4()
        service = Mock(draft=AsyncMock(return_value=[{"start": 0, "end": 2, "text": "hi"}]))
        with patch.object(short_routes, "ShortService", return_value=service):
            self.assertEqual(self.send("GET", f"/videos/{video_id}/shorts/draft?start_time=0&end_time=5").status_code, 422)
            ok = self.send("GET", f"/videos/{video_id}/shorts/draft?start_time=0&end_time=30")
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json()["captions"][0]["text"], "hi")
            limiter.reset()
            for _ in range(60):
                self.assertEqual(self.send("GET", f"/videos/{video_id}/shorts/draft?start_time=0&end_time=30").status_code, 200)
            self.assertEqual(self.send("GET", f"/videos/{video_id}/shorts/draft?start_time=0&end_time=30").status_code, 429)

    def test_create_accepts_a_styled_request_and_rejects_a_bad_one(self):
        self.user = uuid.uuid4()
        video_id = uuid.uuid4()
        bad = self.send("POST", f"/videos/{video_id}/shorts",
                        {"start_time": 0, "end_time": 30, "style": {"font": "nope"}})
        self.assertEqual(bad.status_code, 422)


if __name__ == "__main__":
    unittest.main()
