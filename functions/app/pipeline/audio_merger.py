"""Song Merger: fetches the chosen sections, trims them and joins them into one audio file.

Sources are never decoded to intermediate files: every section is trimmed and
resampled inside one FFmpeg filter graph, so disk use stays near the size of
the inputs and the result.
"""
import math
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
from app.pipeline.youtube_downloader import pot_cli_args

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


def _probe(ffprobe, path, *entries):
    result = subprocess.run([ffprobe, "-v", "error", *entries, "-of", "csv=p=0", str(path)],
                            capture_output=True, text=True, timeout=60, check=True)
    return [line.strip().strip(",") for line in result.stdout.splitlines() if line.strip().strip(",")]


def probe_duration(path, ffprobe):
    try:
        lines = _probe(ffprobe, path, "-show_entries", "format=duration")
        try:
            duration = float(lines[0])
        except (IndexError, ValueError):
            # Browser recordings (MediaRecorder WebM) carry no length: use the last audio packet's time.
            lines = _probe(ffprobe, path, "-select_streams", "a:0", "-show_entries", "packet=pts_time")
            duration = float(lines[-1])
    except (subprocess.SubprocessError, ValueError, IndexError):
        raise MergeError("INVALID_AUDIO") from None
    if duration <= 0:
        raise MergeError("INVALID_AUDIO")
    return duration


def fetch_youtube_section(url, start, end, directory, index, cookie_path, timeout):
    """Downloads only [start, end] (whole seconds) of the video's best audio."""
    prefix = f"yt{index}"
    _run([sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-warnings",
          "--cookies", str(cookie_path), "--js-runtimes", "deno", *pot_cli_args(),
          "--socket-timeout", str(settings.download_timeout_seconds),
          "--retries", str(settings.download_retries),
          "--download-sections", f"*{start}-{end}", "--force-keyframes-at-cuts",
          "-f", "ba/b", "-o", f"{prefix}.%(ext)s", url], directory, timeout)
    found = [p for p in Path(directory).glob(f"{prefix}.*") if p.suffix not in {".part", ".ytdl"}]
    if len(found) != 1:
        raise RuntimeError("Source audio is unavailable.")
    return found[0]


def _time(seconds):
    """Seconds for an FFmpeg argument: exact to a millisecond, without trailing zeros."""
    return f"{seconds:.3f}".rstrip("0").rstrip(".")


def _effects(length, volume=100, fade_in=0, fade_out=0):
    """Filters for one section: loudness, then fades at its two edges."""
    filters = []
    if volume != 100:
        filters.append(f"volume={volume / 100:g}")
    if fade_in:
        filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out:
        filters.append(f"afade=t=out:st={_time(max(length - fade_out, 0))}:d={fade_out}")
    return "".join(f",{name}" for name in filters)


def build_merge_command(ffmpeg, inputs, output, output_format, crossfade):
    """inputs: [(path, start, length[, volume, fade_in, fade_out])] in play order.
    Pure, so it can be tested without FFmpeg."""
    args = [ffmpeg, "-y", "-v", "error"]
    chains = []
    for i, (path, start, length, *effects) in enumerate(inputs):
        if start:
            args += ["-ss", _time(start)]
        args += ["-t", _time(length), "-i", str(Path(path).resolve())]
        chains.append(f"[{i}:a:0]aresample=44100,aformat=channel_layouts=stereo{_effects(length, *effects)}[a{i}]")
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


def merge_audio(tracks, local_paths, output_format, crossfade, directory):
    """tracks: stored track dicts in play order; local_paths: {track index: local
    file} for uploads and for YouTube tracks whose audio is already stored. Any
    other YouTube track is fetched. Returns the path of the merged file."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg is required.")
    directory = Path(directory)
    budget = _Budget(settings.audio_merge_timeout_seconds)
    inputs = []
    cookie_path, secret_id, cookies = None, None, None
    durations = {}
    try:
        if any(index not in local_paths for index in range(len(tracks))):
            secret_id, cookies = secret_manager_client.get_youtube_cookie()
            cookie_path = directory / "cookies.txt"
            cookie_path.write_text(cookies, encoding="utf-8")
        for index, track in enumerate(tracks):
            start, end = track["start_time"], track["end_time"]
            length = round(end - start, 3)
            path = local_paths.get(index)
            if path is None:
                # Whole seconds around the section are downloaded; FFmpeg then cuts to the millisecond.
                first = math.floor(start)
                path = fetch_youtube_section(track["url"], first, math.ceil(end), directory, index, cookie_path, budget.left())
                begin = round(start - first, 3)
                available = probe_duration(path, ffprobe) - begin
            else:
                # Several sections may come from one file; measure it once.
                if path not in durations:
                    durations[path] = probe_duration(path, ffprobe)
                available = durations[path] - start
                begin = start
            if available < length - END_TOLERANCE_SECONDS:
                raise MergeError("INVALID_RANGE")
            inputs.append((path, begin, min(length, available), track.get("volume", 100),
                           track.get("fade_in", 0), track.get("fade_out", 0)))
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
