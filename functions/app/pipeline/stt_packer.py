"""Pack pause-based clips for STT and map compact audio back to video time."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave

from app.core.vad_config import VadSettings
from app.pipeline.audio_chunker import AudioBatch, SAMPLE_RATE


@dataclass(frozen=True)
class SttSpan:
    packed_start: int
    packed_end: int
    source_start: int
    source_end: int


@dataclass(frozen=True)
class SttRequest:
    path: Path
    start_sample: int
    end_sample: int
    first_sequence: int
    last_sequence: int
    spans: tuple[SttSpan, ...]

    @property
    def audio_seconds(self) -> float:
        return self.spans[-1].packed_end / SAMPLE_RATE


def pack_stt_requests(batch: AudioBatch, settings: VadSettings) -> tuple[SttRequest, ...]:
    """Join adjacent VAD clips, retaining at most one second of each silence gap."""
    if len(batch.chunks) != len(batch.paths):
        raise ValueError("Audio manifest/file count mismatch")
    if not batch.chunks:
        return ()
    max_samples = min(int(settings.stt_request_seconds * SAMPLE_RATE),
                      (settings.stt_request_bytes - 44) // 2)
    requests: list[SttRequest] = []
    members: list[tuple] = []
    packed_samples = 0
    source_end = 0

    def write_group() -> None:
        if not members:
            return
        first, last = members[0][0], members[-1][0]
        output = batch.directory / f"stt_{first.sequence_number:04d}_{last.sequence_number:04d}.wav"
        spans = []
        position = 0
        with wave.open(str(output), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(SAMPLE_RATE)
            for chunk, path, clip_start, gap in members:
                if gap:
                    audio.writeframes(bytes(gap * 2))
                    position += gap
                with wave.open(str(path), "rb") as clip:
                    if clip.getnchannels() != 1 or clip.getsampwidth() != 2 or clip.getframerate() != SAMPLE_RATE:
                        raise ValueError("VAD WAV format mismatch")
                    if clip.getnframes() != chunk.end_sample - chunk.start_sample:
                        raise ValueError("VAD WAV duration mismatch")
                    clip.setpos(clip_start - chunk.start_sample)
                    frames = clip.readframes(chunk.end_sample - clip_start)
                if len(frames) != (chunk.end_sample - clip_start) * 2:
                    raise ValueError("VAD WAV duration mismatch")
                audio.writeframes(frames)
                new_position = position + (chunk.end_sample - clip_start)
                spans.append(SttSpan(position, new_position, clip_start, chunk.end_sample))
                position = new_position
        if output.stat().st_size > settings.stt_request_bytes:
            raise ValueError("Packed STT request exceeds file size limit")
        requests.append(SttRequest(output, spans[0].source_start, spans[-1].source_end,
                                   first.sequence_number, last.sequence_number, tuple(spans)))

    previous = None
    for chunk, path in zip(batch.chunks, batch.paths, strict=True):
        if previous is not None and (chunk.sequence_number != previous.sequence_number + 1
                                     or chunk.start_sample < previous.start_sample):
            raise ValueError("VAD chunks must be ordered")
        clip_start = max(chunk.start_sample, source_end) if previous else chunk.start_sample
        if clip_start >= chunk.end_sample:
            previous = chunk
            continue
        gap = min(max(0, clip_start - source_end), SAMPLE_RATE) if members else 0
        needed = chunk.end_sample - clip_start + gap
        if packed_samples + needed > max_samples and members:
            write_group()
            members = []
            packed_samples = 0
            gap = 0
            needed = chunk.end_sample - clip_start
        if needed > max_samples:
            raise ValueError("Single VAD chunk exceeds STT request limit")
        members.append((chunk, path, clip_start, gap))
        packed_samples += needed
        source_end = max(source_end, chunk.end_sample)
        previous = chunk
    write_group()
    return tuple(requests)


def map_request_words(request: SttRequest, words: list[dict]) -> list[dict]:
    """Convert request-local word times into absolute video timestamps."""
    from math import isfinite

    mapped = []
    for word in words:
        start, end = float(word["start"]), float(word["end"])
        if not (isfinite(start) and isfinite(end) and 0 <= start < end <= request.audio_seconds + 0.25):
            continue
        middle = (start + end) * SAMPLE_RATE / 2
        span = next((span for span in request.spans if span.packed_start <= middle < span.packed_end), None)
        if span is None:
            continue
        text = word["word"].strip()
        if text:
            source_start = (span.source_start + max(start * SAMPLE_RATE - span.packed_start, 0)) / SAMPLE_RATE
            source_end = (span.source_start + min(end * SAMPLE_RATE - span.packed_start,
                                                  span.packed_end - span.packed_start)) / SAMPLE_RATE
            if source_end > source_start:
                mapped.append({"text": text, "start": source_start, "end": source_end})
    return mapped
