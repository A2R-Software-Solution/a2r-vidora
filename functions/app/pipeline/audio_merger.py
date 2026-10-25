"""Song Merger: fetches the chosen sections, trims them and joins them into one audio file.

Sources are never decoded to intermediate files: every section is trimmed and
resampled inside one FFmpeg filter graph, so disk use stays near the size of
the inputs and the result.
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path
from app.core.config import settings
from app.integration import secret_manager_client
from app.middleware.logging import logger
# Bounded subprocess helper shared with the Shorts renderer (media tooling only).
from app.pipeline.short_renderer import _run

# Sources may fall a little short of the requested end (keyframe cuts, rounding).
END_TOLERANCE_SECONDS = 1.5
ENCODERS = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
    "m4a": ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"],
}


class MergeError(Exception):
    """A failure with a stable code stored on the job (INVALID_RANGE, INVALID_AUDIO)."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class _Budget:
    def __init__(self, seconds):
        self._deadline = time.monotonic() + seconds

    def left(self):
        remaining = self._deadline - time.monotonic()
        if remaining < 5:
            raise RuntimeError("Media operation timed out.")
        return remaining


def probe_duration(path, ffprobe):
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30, check=True)
        duration = float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        raise MergeError("INVALID_AUDIO") from None
    if duration <= 0:
        raise MergeError("INVALID_AUDIO")
    return duration


def fetch_youtube_section(url, start, end, directory, index, cookie_path, timeout):
    """Downloads only [start, end] of the video's best audio."""
    prefix = f"yt{index}"
    _run([sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-warnings",
          "--cookies", str(cookie_path), "--js-runtimes", "deno",
          "--socket-timeout", str(settings.download_timeout_seconds),
          "--retries", str(settings.download_retries),
          "--download-sections", f"*{start}-{end}", "--force-keyframes-at-cuts",
          "-f", "ba/b", "-o", f"{prefix}.%(ext)s", url], directory, timeout)
    found = [p for p in Path(directory).glob(f"{prefix}.*") if p.suffix not in {".part", ".ytdl"}]
    if len(found) != 1:
        raise RuntimeError("Source audio is unavailable.")
    return found[0]


def build_merge_command(ffmpeg, inputs, output, output_format, crossfade):
    """inputs: [(path, start, length)] in play order. Pure, so it can be tested without FFmpeg."""
    args = [ffmpeg, "-y", "-v", "error"]
    for path, start, length in inputs:
        if start:
            args += ["-ss", str(start)]
        args += ["-t", str(length), "-i", str(Path(path).resolve())]
    chains = [f"[{i}:a:0]aresample=44100,aformat=channel_layouts=stereo[a{i}]" for i in range(len(inputs))]
    count = len(inputs)
    if crossfade:
        previous = "a0"
        for i in range(1, count):
            label = "out" if i == count - 1 else f"x{i}"
            chains.append(f"[{previous}][a{i}]acrossfade=d={crossfade}:c1=tri:c2=tri[{label}]")
            previous = label
    else:
        joined = "".join(f"[a{i}]" for i in range(count))
        chains.append(f"{joined}concat=n={count}:v=0:a=1[out]")
    args += ["-filter_complex", ";".join(chains), "-map", "[out]", "-vn",
             "-filter_complex_threads", "1", "-threads", "2", *ENCODERS[output_format], str(Path(output).resolve())]
    return args


def merge_audio(tracks, upload_paths, output_format, crossfade, directory):
    """tracks: stored track dicts in play order; upload_paths: {track index: local file}.
    Returns the path of the merged file."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg is required.")
    directory = Path(directory)
    budget = _Budget(settings.audio_merge_timeout_seconds)
    inputs = []
    cookie_path, secret_id, cookies = None, None, None
    try:
        if any(t["source"] == "youtube" for t in tracks):
            secret_id, cookies = secret_manager_client.get_youtube_cookie()
            cookie_path = directory / "cookies.txt"
            cookie_path.write_text(cookies, encoding="utf-8")
        for index, track in enumerate(tracks):
            start, end = track["start_time"], track["end_time"]
            length = end - start
            if track["source"] == "youtube":
                path = fetch_youtube_section(track["url"], start, end, directory, index, cookie_path, budget.left())
                available = probe_duration(path, ffprobe)
                begin = 0
            else:
                path = upload_paths[index]
                available = probe_duration(path, ffprobe) - start
                begin = start
            if available < length - END_TOLERANCE_SECONDS:
                raise MergeError("INVALID_RANGE")
            inputs.append((path, begin, min(length, available)))
        if cookie_path is not None:
            refreshed = cookie_path.read_text(encoding="utf-8")
            if refreshed != cookies:
                secret_manager_client.update_youtube_cookie(secret_id, refreshed)
    finally:
        if cookie_path is not None:
            cookie_path.unlink(missing_ok=True)
    output = directory / f"merged.{output_format}"
    _run(build_merge_command(ffmpeg, inputs, output, output_format, crossfade), directory, budget.left())
    if not output.exists() or not output.stat().st_size:
        raise RuntimeError("Merged audio is empty.")
    logger.info("audio_merge_rendered tracks=%s bytes=%s", len(inputs), output.stat().st_size)
    return output
