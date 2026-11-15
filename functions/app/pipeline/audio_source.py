"""Song Merger Pro editor: fetches one YouTube track's audio once.

The browser cannot read YouTube audio, so the editor's waveform and preview
come from here: the untouched best audio (reused by the merge, so YouTube is
not asked again), a small preview MP3, and waveform peaks.
"""
from __future__ import annotations

import shutil
import subprocess
from array import array
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.core.config import settings
from app.pipeline.audio_merger import probe_duration
from app.pipeline.media_downloader import _base_options, _check_media, _to_download_error
from app.pipeline.short_renderer import _run
from app.pipeline.youtube_downloader import DownloadError, with_cookie_failover

# Enough detail to zoom in: 50 slices a second, between these bounds.
PEAKS_PER_SECOND = 50
MIN_PEAKS, MAX_PEAKS = 800, 45000
PEAK_SAMPLE_RATE = 4000
# Low enough that the preview is no substitute for a real download.
PREVIEW_ARGS = ["-vn", "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "64k"]


@dataclass(frozen=True)
class PreparedSource:
    video_id: str
    title: str | None
    duration: int
    original: Path
    preview: Path
    peaks: list[int]


def peak_count(seconds: float) -> int:
    return min(max(round(seconds * PEAKS_PER_SECOND), MIN_PEAKS), MAX_PEAKS)


def peaks_from_samples(samples, count: int = MIN_PEAKS) -> list[int]:
    """Loudest sample of each of `count` equal slices, scaled so the loudest
    slice is 100. `samples` is a sequence of signed 16-bit values."""
    total = len(samples)
    if not total:
        return []
    count = min(count, total)
    peaks = []
    for i in range(count):
        chunk = samples[i * total // count:(i + 1) * total // count]
        peaks.append(max(max(chunk), -min(chunk)))
    loudest = max(peaks) or 1
    return [round(peak * 100 / loudest) for peak in peaks]


def waveform_peaks(path: Path, ffmpeg: str, timeout: float) -> list[int]:
    try:
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(PEAK_SAMPLE_RATE),
             "-f", "s16le", "pipe:1"], capture_output=True, timeout=timeout, check=True)
    except subprocess.SubprocessError:
        raise RuntimeError("Waveform could not be read.") from None
    samples = array("h")
    samples.frombytes(result.stdout[:len(result.stdout) // 2 * 2])
    return peaks_from_samples(samples, peak_count(len(samples) / PEAK_SAMPLE_RATE))


def _fetch(url: str, directory: str, max_seconds: int):
    """Downloads the best audio as YouTube serves it (no re-encoding)."""
    def attempt(cookiefile: str):
        options = _base_options(cookiefile, directory) | {"format": "ba/b"}
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                media = _check_media(ydl.extract_info(url, download=False), max_seconds)
                ydl.download([url])
                return media
        except yt_dlp.utils.DownloadError as exc:
            raise _to_download_error(url, exc) from exc

    media = with_cookie_failover(directory, attempt)
    found = [p for p in Path(directory).glob(f"{media.video_id}.*") if p.suffix not in {".part", ".ytdl", ".txt"}]
    if len(found) != 1:
        raise DownloadError("Source audio is unavailable.")
    return media, found[0]


def prepare_source(url: str, directory: str) -> PreparedSource:
    """Blocking; run it in a thread. The caller owns `directory`."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg is required.")
    timeout = settings.audio_merge_source_timeout_seconds
    media, original = _fetch(url, directory, settings.audio_merge_source_max_seconds)
    preview = Path(directory) / "preview.mp3"
    _run([ffmpeg, "-y", "-v", "error", "-i", str(original.resolve()), *PREVIEW_ARGS, str(preview.resolve())],
         directory, timeout)
    peaks = waveform_peaks(original, ffmpeg, timeout)
    if not peaks or not preview.exists() or not preview.stat().st_size:
        raise RuntimeError("Source audio is empty.")
    return PreparedSource(video_id=media.video_id, title=media.title, duration=int(probe_duration(original, ffprobe)),
                          original=original, preview=preview, peaks=peaks)
