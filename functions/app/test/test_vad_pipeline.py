"""Actual ingestion wiring with mocked external services; no paid provider calls."""
import asyncio
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
import uuid

from app.integration import groq_client
from app.models.video_model import VideoStatus
from app.pipeline import pipeline, transcriber
from app.pipeline.audio_chunker import AudioBatch, AudioChunk, SAMPLE_RATE
from app.pipeline.transcript_assembler import assemble_words
from app.core.config import settings


def chunk(index, start, end):
    return AudioChunk(f"chunk-{index}", index, round(start * SAMPLE_RATE), round(end * SAMPLE_RATE),
                      round(start * SAMPLE_RATE), round(end * SAMPLE_RATE), (index,), False)


class AssemblyTests(unittest.TestCase):
    def test_offsets_overlap_order_and_real_repeated_words(self):
        chunks = (chunk(0, 10, 40), chunk(1, 39, 60), chunk(2, 80, 90))
        results = {
            "chunk-2": [{"word": "again", "start": 1, "end": 2}],
            "chunk-0": [{"word": "start", "start": 0, "end": 1},
                        {"word": "left", "start": 29.1, "end": 29.3},
                        {"word": "right", "start": 29.6, "end": 29.8}],
            "chunk-1": [{"word": "left", "start": 0.1, "end": 0.3},
                        {"word": "right", "start": 0.6, "end": 0.8},
                        {"word": "again", "start": 10, "end": 11}],
        }
        assembled = assemble_words(chunks, results)
        self.assertEqual([s["text"] for s in assembled], ["start", "left", "right", "again", "again"])
        self.assertEqual([s["start"] for s in assembled], [10, 39.1, 39.6, 49, 81])

    def test_missing_results_and_bad_sequence_fail(self):
        chunks = (chunk(0, 0, 10), chunk(1, 20, 30))
        with self.assertRaises(ValueError):
            assemble_words(chunks, {"chunk-0": []})
        with self.assertRaises(ValueError):
            assemble_words((chunk(1, 0, 10),), {"chunk-1": []})

    def test_invalid_word_timestamps_are_skipped_without_losing_valid_words(self):
        valid = {"word": "good", "start": 1, "end": 2}
        for start, end in [(-1, 1), (2, 1), (0, float("nan")), (0, 11)]:
            with self.subTest(start=start, end=end):
                assembled = assemble_words(
                    (chunk(0, 0, 10),),
                    {"chunk-0": [valid, {"word": "bad", "start": start, "end": end}]},
                )
                self.assertEqual(assembled, [{"text": "good", "start": 1, "end": 2}])


class ChunkTranscriptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_speech_skips_provider(self):
        with patch.object(transcriber, "transcribe_audio_words", AsyncMock()) as provider:
            with self.assertRaises(groq_client.EmptyTranscriptionError):
                await transcriber.transcribe_chunks(AudioBatch(Path("."), (), ()))
        provider.assert_not_awaited()

    async def test_bounded_parallel_calls_preserve_chronological_assembly(self):
        chunks = tuple(chunk(i, i * 10, (i + 1) * 10) for i in range(3))
        batch = AudioBatch(Path("."), chunks, tuple(Path(f"{i}.wav") for i in range(3)))
        active, peak = 0, 0
        async def stt(path):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1
            return [{"word": path, "start": 1, "end": 2}]
        with patch.object(transcriber, "transcribe_audio_words", AsyncMock(side_effect=stt)) as provider:
            segments = await transcriber.transcribe_chunks(batch)
        self.assertEqual(peak, min(settings.stt_concurrency, len(chunks)))
        self.assertEqual(provider.await_count, 3)
        self.assertEqual([s["start"] for s in segments], [1, 11, 21])
        with patch.object(transcriber, "transcribe_audio_words", AsyncMock(side_effect=[[], RuntimeError("network"), []])) as provider:
            with self.assertRaises(ExceptionGroup):
                await transcriber.transcribe_chunks(batch)
        self.assertGreaterEqual(provider.await_count, 2)
        self.assertLessEqual(provider.await_count, len(chunks))

    async def test_groq_wav_word_request_and_missing_timing_rejection(self):
        create = AsyncMock(return_value=SimpleNamespace(words=[{"word": "hello", "start": 0, "end": 1}], text="hello"))
        client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
        async def call(operation):
            return await operation(client)
        with patch.object(groq_client, "_with_groq_client", call), patch.object(Path, "read_bytes", return_value=b"wav"):
            words = await groq_client.transcribe_audio_words("chunk.wav")
            self.assertEqual(words[0]["word"], "hello")
            self.assertEqual(create.call_args.kwargs["file"][2], "audio/wav")
            self.assertEqual(create.call_args.kwargs["timestamp_granularities"], ["word"])
            create.return_value = SimpleNamespace(words=None, text="hello")
            with self.assertRaises(groq_client.GroqRequestError):
                await groq_client.transcribe_audio_words("chunk.wav")


class IngestionWiringTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.video = SimpleNamespace(
            id=uuid.uuid4(), status=VideoStatus.PROCESSING, user_id=None,
            processing_total_chunks=0,
        )
        self.service = Mock(get_for_processing=AsyncMock(return_value=self.video),
            mark_metadata=AsyncMock(return_value=self.video), mark_completed=AsyncMock(return_value=self.video),
            mark_failed=AsyncMock(), mark_progress=AsyncMock(return_value=self.video))
        self.chunks = Mock(replace_all_for_video=AsyncMock())
        self.db = Mock(rollback=AsyncMock())
        self.stack.enter_context(patch.object(pipeline, "VideoService", return_value=self.service))
        self.stack.enter_context(patch.object(pipeline, "TranscriptChunkService", return_value=self.chunks))
        self.stack.enter_context(patch.object(pipeline, "download_audio", AsyncMock(return_value=SimpleNamespace(
            audio_path=Path("download.mp3"), title="Test", duration=60))))
        self.prepared_path = None
        async def prepare(source, *, output_root, **kwargs):
            self.prepared_path = output_root
            return AudioBatch(output_root, (chunk(0, 0, 10),), (output_root / "0.wav",))
        self.prepare = self.stack.enter_context(patch.object(pipeline.audio_chunker, "prepare_audio_async", AsyncMock(side_effect=prepare)))
        self.stt = self.stack.enter_context(patch.object(pipeline.transcriber, "transcribe_chunks", AsyncMock(return_value=[
            {"text": "hello", "start": 1, "end": 2}])))
        self.embed = self.stack.enter_context(patch.object(pipeline.embedder, "embed_chunks", AsyncMock(return_value=[
            {"chunk_text": "hello", "start_time": 1, "end_time": 2, "embedding": [0.0] * 384}])))
        self.summary = self.stack.enter_context(patch.object(pipeline.summarizer, "summarize", AsyncMock(return_value="Summary")))

    async def test_real_pipeline_uses_vad_and_publishes_complete_result(self):
        result = await pipeline.run_pipeline(self.video.id, "https://youtu.be/yYF2Vf1Gc14", db=self.db)
        self.assertIs(result, self.video)
        self.prepare.assert_awaited_once()
        self.assertEqual(self.prepare.call_args.kwargs["source_id"], self.video.id)
        self.stt.assert_awaited_once()
        self.chunks.replace_all_for_video.assert_awaited_once()
        self.assertFalse(self.chunks.replace_all_for_video.call_args.kwargs["commit"])
        self.service.mark_completed.assert_awaited_once_with(self.video, summary="Summary")
        self.service.mark_failed.assert_not_awaited()
        self.assertFalse(self.prepared_path.exists())

    async def test_completed_video_is_not_processed_again(self):
        self.video.status = VideoStatus.COMPLETED
        await pipeline.run_pipeline(self.video.id, "url", db=self.db)
        self.prepare.assert_not_awaited()
        self.stt.assert_not_awaited()

    async def test_stt_and_summary_failures_do_not_publish_partial_transcript(self):
        for failing in (self.stt, self.summary):
            with self.subTest(stage=failing):
                failing.side_effect = RuntimeError("provider unavailable")
                with self.assertRaises(pipeline.PipelineError):
                    await pipeline.run_pipeline(self.video.id, "url", db=self.db)
                self.chunks.replace_all_for_video.assert_not_awaited()
                self.service.mark_completed.assert_not_awaited()
                self.assertFalse(self.prepared_path.exists())
                failing.side_effect = None
        self.assertEqual(self.service.mark_failed.await_count, 2)

    async def test_cancellation_cleans_temp_and_marks_failure(self):
        self.stt.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await pipeline.run_pipeline(self.video.id, "url", db=self.db)
        self.service.mark_failed.assert_awaited_once()
        self.chunks.replace_all_for_video.assert_not_awaited()
        self.assertFalse(self.prepared_path.exists())
