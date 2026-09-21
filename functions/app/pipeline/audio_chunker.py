"""Production VAD audio preparation, also runnable as a local listening preview."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import wave
import threading
from functools import lru_cache

# Support direct execution before importing the shared application configuration.
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.vad_config import VadSettings

# Local preview inputs: set ONE, or supply --audio / --youtube on the command line.
YOUTUBE_URL = ""
LOCAL_AUDIO_PATH = ""
FUNCTIONS_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = FUNCTIONS_ROOT / "audio-preview.local"
SAMPLE_RATE = 16000


_vad_lock = threading.Lock()


@lru_cache(maxsize=1)
def _load_vad_model():
    from silero_vad import load_silero_vad
    return load_silero_vad(onnx=False)


@dataclass(frozen=True)
class AudioChunk:
    id: str
    sequence_number: int
    start_sample: int
    end_sample: int
    speech_start_sample: int
    speech_end_sample: int
    speech_region_indices: tuple[int, ...]
    forced_split: bool
    boundary_reason: str = "speech_end"


@dataclass(frozen=True)
class AudioBatch:
    directory: Path
    chunks: tuple[AudioChunk, ...]
    paths: tuple[Path, ...]


def plan_vad_chunks(regions: list[dict], total_samples: int, source_id: uuid.UUID,
                    settings: VadSettings) -> list[AudioChunk]:
    """Merge adjacent speech across small gaps, preserving the original timeline.

    Prefer existing speech boundaries for size limits. Only an individual region
    longer than the cap is cut mid-speech, with configurable overlap. Padding is
    included in the maximum exported duration. Silence is never concatenated out.
    """
    pad = settings.speech_pad_ms * SAMPLE_RATE // 1000
    gap_limit = settings.merge_pause_ms * SAMPLE_RATE // 1000
    overlap = settings.split_overlap_ms * SAMPLE_RATE // 1000
    budget = int(settings.max_chunk_seconds * SAMPLE_RATE) - 2 * pad
    target = min(budget, int(settings.group_target_seconds * SAMPLE_RATE))
    groups = []
    previous_end = 0
    for i, region in enumerate(regions):
        start, end = region["start"], region["end"]
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= total_samples:
            raise ValueError("VAD returned invalid sample bounds")
        if start < previous_end:
            raise ValueError("VAD regions must be ordered and non-overlapping")
        previous_end = end
        # The target is deliberately soft: a final complete utterance may take
        # a group past it, but never past the hard export budget.
        if (groups and groups[-1][1] - groups[-1][0] < target
                and start - groups[-1][1] <= gap_limit
                and end - groups[-1][0] <= budget):
            groups[-1][1] = end
            groups[-1][2].append(i)
        else:
            groups.append([start, end, [i]])
    chunks = []
    for start, end, indices in groups:
        forced = end - start > budget
        cursor = start
        while cursor < end:
            stop = min(cursor + budget, end)
            clip_start, clip_end = max(0, cursor - pad), min(total_samples, stop + pad)
            index = len(chunks)
            identifier = uuid.uuid5(source_id, f"{index}:{clip_start}:{clip_end}")
            boundary_reason = "forced_max_duration" if forced and stop < end else "speech_end"
            if len(indices) > 1 and stop == end:
                boundary_reason = "group_end"
            chunks.append(AudioChunk(str(identifier), index, clip_start, clip_end, cursor, stop,
                                      tuple(indices), forced, boundary_reason))
            if stop == end:
                break
            cursor = stop - overlap
    return chunks


def decode_audio(source: Path, destination: Path, max_seconds: int) -> None:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("ffmpeg is required on PATH")
    # Read at most the budget + 1 second; reject overlong input instead of silently truncating.
    subprocess.run([binary, "-nostdin", "-v", "error", "-y", "-i", str(source),
                    "-t", str(max_seconds + 1), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
                    "-c:a", "pcm_s16le", str(destination)], check=True, capture_output=True,
                   timeout=180)


def detect_speech(pcm: bytes, settings: VadSettings) -> list[dict]:
    try:
        import numpy as np
        import torch
        from silero_vad import get_speech_timestamps
    except ImportError as exc:
        raise RuntimeError("Install VAD dependencies from functions/requirements-vad.txt") from exc
    audio = torch.from_numpy(np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0)
    # Ask Silero to close an overlong region at its most suitable detected
    # silence before the planner has to make a mechanical mid-speech cut.  The
    # planner retains the final hard cap (including export padding).
    usable_speech_seconds = settings.max_chunk_seconds - (2 * settings.speech_pad_ms / 1000)
    # The pip package bundles its model; no torch.hub/GitHub runtime download.
    # Silero has mutable recurrent state. Serialize inference across requests and
    # reuse a single model per process, with no event-loop blocking in production.
    with _vad_lock:
        return get_speech_timestamps(audio, _load_vad_model(), sampling_rate=SAMPLE_RATE,
            threshold=settings.threshold, neg_threshold=settings.neg_threshold,
            min_speech_duration_ms=settings.min_speech_ms,
            min_silence_duration_ms=settings.min_silence_ms, speech_pad_ms=0,
            max_speech_duration_s=usable_speech_seconds,
            use_max_poss_sil_at_max_speech=True,
            return_seconds=False)


def prepare_audio(source: Path, *, output_root: Path,
                  settings: VadSettings, source_id: uuid.UUID | None = None,
                  verbose: bool = False) -> AudioBatch:
    settings = settings or VadSettings()
    source = Path(source).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="vidora_vad_") as temporary:
        normalized = Path(temporary) / "normalized.wav"
        decode_audio(source, normalized, settings.max_audio_seconds)
        with wave.open(str(normalized), "rb") as audio:
            total_samples = audio.getnframes()
            if not 0 < total_samples <= settings.max_audio_seconds * SAMPLE_RATE:
                raise ValueError(f"Audio must be nonempty and at most {settings.max_audio_seconds} seconds")
            pcm = audio.readframes(total_samples)
        if verbose:
            print("Detecting speech with Silero VAD...", flush=True)
        regions = detect_speech(pcm, settings)
        source_hash = hashlib.sha256(pcm).hexdigest()
        source_id = source_id or uuid.uuid5(uuid.NAMESPACE_URL, source_hash)
        chunks = plan_vad_chunks(regions, total_samples, source_id, settings)
        output_dir = Path(output_root) / f"{source.stem[:60]}_{uuid.uuid4().hex[:12]}"
        output_dir.mkdir(parents=True, exist_ok=False)
        manifest = {"source_file": source.name, "source_id": str(source_id), "pcm_sha256": source_hash,
                    "sample_rate": SAMPLE_RATE, "duration_seconds": total_samples / SAMPLE_RATE,
                    "detector": "silero-vad-6.2.2", "settings": settings.model_dump(),
                    "speech_regions": [{"index": i, "start_sample": r["start"], "end_sample": r["end"],
                                        "start_seconds": r["start"] / SAMPLE_RATE, "end_seconds": r["end"] / SAMPLE_RATE}
                                       for i, r in enumerate(regions)], "chunks": []}
        paths = []
        if verbose:
            print(f"{len(regions)} speech regions -> {len(chunks)} merged chunks. Output: {output_dir}", flush=True)
        for chunk in chunks:
            start, end = chunk.start_sample / SAMPLE_RATE, chunk.end_sample / SAMPLE_RATE
            filename = f"chunk_{chunk.sequence_number:04d}_{start:.3f}s-{end:.3f}s.wav"
            paths.append(output_dir / filename)
            with wave.open(str(output_dir / filename), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(SAMPLE_RATE)
                audio.writeframes(pcm[chunk.start_sample * 2:chunk.end_sample * 2])
            manifest["chunks"].append({**asdict(chunk), "start_seconds": start, "end_seconds": end,
                                       "duration_seconds": end - start, "file": filename})
            if verbose:
                print(f"  {filename}" + (" [long speech: forced split]" if chunk.forced_split else ""), flush=True)
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if not chunks and verbose:
            print("No speech detected. Manifest saved; no audio chunks produced.", flush=True)
        return AudioBatch(output_dir, tuple(chunks), tuple(paths))


def chunk_local_audio(source: Path, *, output_root: Path = OUTPUT_ROOT,
                      settings: VadSettings | None = None) -> Path:
    return prepare_audio(source, output_root=output_root, settings=settings or VadSettings(), verbose=True).directory


async def prepare_audio_async(source: Path, *, output_root: Path,
                              settings: VadSettings, source_id: uuid.UUID) -> AudioBatch:
    import asyncio
    work = asyncio.create_task(asyncio.to_thread(prepare_audio, source,
        output_root=output_root, settings=settings, source_id=source_id))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        # Python cannot cancel a running FFmpeg/inference thread. Let it finish
        # before the caller removes its temp directory (including on Windows).
        try:
            await work
        except Exception:
            pass
        raise


async def preview_youtube(url: str, output_root: Path) -> Path:
    import os
    from app.core.config import settings as app_settings
    from app.pipeline.youtube_downloader import download_audio, make_temp_dir
    from app.utils.youtube import extract_youtube_id

    extract_youtube_id(url)
    if app_settings.google_credentials_path and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        credentials = Path(app_settings.google_credentials_path)
        if not credentials.is_absolute():
            credentials = FUNCTIONS_ROOT / credentials
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials)
    with make_temp_dir() as temporary:
        downloaded = await download_audio(url, output_dir=temporary)
        return chunk_local_audio(downloaded.audio_path, output_root=output_root)


def main() -> int:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--audio", type=Path, help="Local audio/video file; no Google credentials needed")
    inputs.add_argument("--youtube", help="YouTube URL; uses existing cookie/Secret Manager setup")
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    if args.audio is None and args.youtube is None:
        if LOCAL_AUDIO_PATH and YOUTUBE_URL:
            parser.error("Set only one of LOCAL_AUDIO_PATH or YOUTUBE_URL")
        args.audio = Path(LOCAL_AUDIO_PATH) if LOCAL_AUDIO_PATH else None
        args.youtube = YOUTUBE_URL.strip() or None
    if args.audio is None and args.youtube is None:
        parser.error("Supply --audio PATH / --youtube URL, or set LOCAL_AUDIO_PATH / YOUTUBE_URL at the top")
    try:
        if args.audio is not None:
            chunk_local_audio(args.audio, output_root=args.output)
        else:
            asyncio.run(preview_youtube(args.youtube, args.output))
    except Exception as exc:
        # Do not print provider bodies or credentials from the existing downloader.
        if type(exc).__name__ == "PermissionDenied":
            print("Preview blocked: Google cookie-secret access denied. Use --audio with a local file to test VAD without Google access.")
        elif isinstance(exc, (ValueError, RuntimeError, FileNotFoundError)):
            print(f"Preview failed: {exc}")
        else:
            print(f"Preview failed ({type(exc).__name__}). Check audio input, FFmpeg and downloader configuration.")
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(FUNCTIONS_ROOT))
    raise SystemExit(main())
