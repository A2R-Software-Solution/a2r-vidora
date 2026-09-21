"""Local VAD/merge tests; no cloud, database, or paid STT requests."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid
import wave

from pydantic import ValidationError
from app.pipeline.audio_chunker import VadSettings, SAMPLE_RATE, chunk_local_audio, detect_speech, plan_vad_chunks


def region(start, end):
    return {"start": int(start * SAMPLE_RATE), "end": int(end * SAMPLE_RATE)}


class VadChunkTests(unittest.TestCase):
    def setUp(self):
        self.source_id = uuid.uuid4()
        self.settings = VadSettings(_env_file=None)

    def test_short_pauses_merge_and_long_pauses_split_without_time_compression(self):
        regions = [region(1, 2), region(2.5, 4), region(5, 6)]
        chunks = plan_vad_chunks(regions, 7 * SAMPLE_RATE, self.source_id, self.settings)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].speech_region_indices, (0, 1))
        self.assertEqual(chunks[0].speech_start_sample, SAMPLE_RATE)
        self.assertEqual(chunks[0].speech_end_sample, 4 * SAMPLE_RATE)
        self.assertAlmostEqual(chunks[0].start_sample / SAMPLE_RATE, 0.85)
        self.assertAlmostEqual(chunks[0].end_sample / SAMPLE_RATE, 4.15)
        self.assertAlmostEqual(chunks[1].start_sample / SAMPLE_RATE, 4.85)

    def test_pause_threshold_is_inclusive_and_configurable(self):
        regions = [region(0, 1), region(1.6, 2)]
        self.assertEqual(len(plan_vad_chunks(regions, 3 * SAMPLE_RATE, self.source_id, self.settings)), 1)
        settings = VadSettings(_env_file=None, merge_pause_ms=500)
        self.assertEqual(len(plan_vad_chunks(regions, 3 * SAMPLE_RATE, self.source_id, settings)), 2)

    def test_group_target_is_soft_but_prevents_unbounded_merging(self):
        settings = VadSettings(_env_file=None, group_target_seconds=20)
        regions = [region(0, 10), region(10.2, 23), region(23.2, 25)]
        chunks = plan_vad_chunks(regions, 26 * SAMPLE_RATE, self.source_id, settings)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].speech_region_indices, (0, 1))
        self.assertEqual(chunks[0].boundary_reason, "group_end")
        self.assertEqual(chunks[1].speech_region_indices, (2,))

    def test_negative_threshold_must_remain_below_start_threshold(self):
        with self.assertRaises(ValidationError):
            VadSettings(_env_file=None, threshold=0.5, neg_threshold=0.5)

    def test_long_speech_forced_split_preserves_coverage_and_caps_duration(self):
        chunks = plan_vad_chunks([region(0, 70)], 70 * SAMPLE_RATE, self.source_id, self.settings)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(c.forced_split for c in chunks))
        self.assertTrue(all(c.boundary_reason == "forced_max_duration" for c in chunks[:-1]))
        self.assertEqual(chunks[0].start_sample, 0)
        self.assertEqual(chunks[-1].end_sample, 70 * SAMPLE_RATE)
        for c in chunks:
            self.assertLessEqual(c.end_sample - c.start_sample, 30 * SAMPLE_RATE)
        for previous, current in zip(chunks, chunks[1:]):
            self.assertEqual(previous.speech_end_sample - current.speech_start_sample, SAMPLE_RATE // 4)

    def test_max_size_prefers_existing_pause_boundary(self):
        chunks = plan_vad_chunks([region(0, 20), region(20.4, 35)], 40 * SAMPLE_RATE, self.source_id, self.settings)
        self.assertEqual(len(chunks), 2)
        self.assertFalse(any(c.forced_split for c in chunks))
        self.assertEqual(chunks[0].speech_end_sample, 20 * SAMPLE_RATE)

    def test_ids_are_stable_and_regions_validated(self):
        regions = [region(0, 1), region(3, 4)]
        chunks = plan_vad_chunks(regions, 5 * SAMPLE_RATE, self.source_id, self.settings)
        self.assertEqual(chunks, plan_vad_chunks(regions, 5 * SAMPLE_RATE, self.source_id, self.settings))
        self.assertEqual([c.sequence_number for c in chunks], [0, 1])
        self.assertNotEqual(chunks[0].id, chunks[1].id)
        self.assertEqual(plan_vad_chunks([], 100, self.source_id, self.settings), [])
        for invalid in [[region(1, 0)], [region(-1, 2)], [region(0, 6)], [region(0, 2), region(1, 3)]]:
            with self.assertRaises(ValueError):
                plan_vad_chunks(invalid, 5 * SAMPLE_RATE, self.source_id, self.settings)

    def test_invalid_settings_rejected(self):
        for values in [{"threshold": 0}, {"threshold": 1}, {"merge_pause_ms": -1},
                       {"merge_pause_ms": 50}, {"max_chunk_seconds": 0.2},
                       {"split_overlap_ms": 30000}, {"speech_pad_ms": -1}]:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                VadSettings(_env_file=None, **values)

    @unittest.skipUnless(shutil.which("ffmpeg"), "Requires FFmpeg")
    def test_exported_wav_manifest_and_actual_duration_agree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.wav"
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=7", str(source)], check=True, capture_output=True)
            with patch("app.pipeline.audio_chunker.detect_speech", return_value=[region(1, 2), region(2.5, 4), region(5, 6)]):
                directory = chunk_local_audio(source, output_root=root / "result", settings=self.settings)
            manifest = json.loads((directory / "manifest.json").read_text())
            self.assertEqual(len(manifest["speech_regions"]), 3)
            self.assertEqual(len(manifest["chunks"]), 2)
            for chunk in manifest["chunks"]:
                with wave.open(str(directory / chunk["file"]), "rb") as audio:
                    self.assertEqual(audio.getnframes(), chunk["end_sample"] - chunk["start_sample"])
                    self.assertEqual(audio.getframerate(), SAMPLE_RATE)
                    self.assertEqual(audio.getnchannels(), 1)

    @unittest.skipUnless(importlib.util.find_spec("silero_vad"), "Install requirements-vad.txt for actual model check")
    def test_real_silero_model_detects_no_speech_in_silence(self):
        self.assertEqual(detect_speech(bytes(SAMPLE_RATE * 2 * 3), self.settings), [])
