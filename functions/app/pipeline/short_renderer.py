"""Bounded subprocesses and temporary files for captioned, styled MP4 clips."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from app.core.config import settings
from app.middleware.logging import logger
from app.pipeline.short_ass import build_ass, output_size
from app.pipeline.short_catalog import FONTS, font_file
from app.pipeline.youtube_downloader import (YouTubeBotChallengeError, is_youtube_bot_challenge, pot_cli_args,
                                             with_cookie_failover)
from app.schemas.short_schema import ShortOptions


def _log_stderr(stderr, reason):
    """Logs the tail of stderr and returns it, so callers can classify the failure."""
    try:
        stderr.seek(0)
        text = stderr.read()[-2000:].decode("utf-8", "replace").strip()
        logger.error("media_command_failed reason=%s stderr=%s", reason, " | ".join(text.splitlines()[-20:]))
        return text
    finally:
        stderr.close()


def _run(args, directory, timeout):
    # Keep stderr so failures are diagnosable; a temp file avoids pipe deadlocks.
    stderr = tempfile.TemporaryFile()
    process = subprocess.Popen(args, cwd=directory, stdout=subprocess.DEVNULL,
                               stderr=stderr, start_new_session=os.name != "nt")
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # yt-dlp can start FFmpeg children; terminate the entire process group.
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        else:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        _log_stderr(stderr, "timed out")
        raise RuntimeError("Media operation timed out.") from None
    if code:
        if is_youtube_bot_challenge(_log_stderr(stderr, f"exit code {code}")):
            raise YouTubeBotChallengeError("YouTube session temporarily unavailable.")
        raise RuntimeError("Media operation failed.")
    stderr.close()


def _srt_time(seconds):
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


_MARKUP = re.compile(r"[<>{}\\]")


def caption_cues(chunks, start, end):
    """Approximate phrase cues from transcript chunks, in seconds from `start`.
    Word timings aren't retained, so each chunk's words are spread evenly."""
    cues = []
    previous_end = 0.0
    for chunk in chunks:
        words = _MARKUP.sub("", chunk.chunk_text).split()
        if not words or chunk.end_time <= chunk.start_time:
            continue
        for index in range(0, len(words), 8):
            left = chunk.start_time + (chunk.end_time - chunk.start_time) * index / len(words)
            right = chunk.start_time + (chunk.end_time - chunk.start_time) * min(index + 8, len(words)) / len(words)
            left, right = max(left, start) - start, min(right, end) - start
            left = max(left, previous_end)
            if right <= left:
                continue
            cues.append({"start": left, "end": right, "text": " ".join(words[index:index + 8])})
            previous_end = right
    return cues


def caption_text(chunks, start, end):
    """The same cues as SRT text."""
    return "\n".join(
        f"{number}\n{_srt_time(cue['start'])} --> {_srt_time(cue['end'])}\n{cue['text']}\n"
        for number, cue in enumerate(caption_cues(chunks, start, end), 1))


_environment_checked = False


def _log_environment(ffmpeg):
    """Once per process: log whether this runtime can render styled captions, so a
    missing encoder, filter or font shows up in the logs instead of as a bare failure."""
    global _environment_checked
    if _environment_checked:
        return
    _environment_checked = True
    try:
        def listing(flag):
            return subprocess.run([ffmpeg, "-hide_banner", flag], capture_output=True, text=True, timeout=20).stdout
        missing_fonts = [key for key in FONTS if not font_file(key).is_file()]
        logger.info("short_render_environment libx264=%s ass_filter=%s missing_fonts=%s",
                    " libx264 " in listing("-encoders"), " ass " in listing("-filters"), missing_fonts or "none")
    except Exception:
        logger.exception("short_render_environment_check_failed")


def prepare_captions(directory, options, cues):
    """Writes captions.ass and the one font file it needs into `directory`."""
    style = options["style"]
    directory = Path(directory)
    (directory / "captions.ass").write_text(build_ass(cues, style, options["ratio"]), encoding="utf-8")
    fonts = directory / "fonts"
    fonts.mkdir(exist_ok=True)
    shutil.copyfile(font_file(style["font"]), fonts / FONTS[style["font"]]["file"])


def render_short(url, start, end, chunks, directory, options=None):
    import sys
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required.")
    _log_environment(ffmpeg)
    directory = Path(directory)
    options = ShortOptions.model_validate(options or {}).model_dump()
    cues = options["captions"] if options["captions"] is not None else caption_cues(chunks, start, end)
    if not cues:
        raise ValueError("No captions available for this range.")
    prepare_captions(directory, options, cues)
    def download(cookie_path):
        # Fetch only the requested section, not a multi-hour source video.
        _run([sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-warnings",
              "--cookies", cookie_path, "--js-runtimes", "deno", *pot_cli_args(),
              "--socket-timeout", str(settings.download_timeout_seconds),
              "--retries", str(settings.download_retries),
              "--download-sections", f"*{start}-{end}", "--force-keyframes-at-cuts",
              "-f", "bv*[height<=720]+ba/b[height<=720]", "--merge-output-format", "mp4",
              "-o", "source.%(ext)s", url], directory, settings.shorts_timeout_seconds // 2)

    # A refused account is set aside and the next one tried, as for analysis; a
    # session refreshed by a successful download is saved back by the helper.
    with_cookie_failover(str(directory), download)
    sources = [p for p in directory.glob("source.*") if p.suffix in {".mp4", ".webm", ".mkv"}]
    if len(sources) != 1:
        raise RuntimeError("Source clip is unavailable.")
    return render_local(sources[0], end - start, directory, ffmpeg, options)


def build_filter(options):
    """The filter graph: fit the picture to the chosen frame, then burn in captions."""
    width, height = output_size(options["ratio"])
    background = options["background"]
    captions = "ass=captions.ass:fontsdir=fonts[out]"
    if background == "fill":
        picture = f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
    elif background == "solid":
        colour = "0x" + options["background_color"].lstrip("#").upper()
        picture = (f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={colour},setsar=1")
    else:
        picture = (
            "[0:v]split=2[bg][fg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=20:2[back];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[front];"
            "[back][front]overlay=(W-w)/2:(H-h)/2,setsar=1")
    return f"{picture},{captions}"


def render_local(source, duration, directory, ffmpeg=None, options=None):
    """Renders `source` into short.mp4. Expects captions.ass and fonts/ in `directory`."""
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    options = ShortOptions.model_validate(options or {}).model_dump()
    output = Path(directory) / "short.mp4"
    _run([ffmpeg, "-y", "-v", "error", "-i", str(Path(source).resolve()),
          "-filter_complex", build_filter(options), "-map", "[out]", "-map", "0:a:0?",
          "-t", str(duration), "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "24", "-pix_fmt", "yuv420p", "-threads", "2", "-filter_complex_threads", "1",
          "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output.resolve())],
         directory, settings.shorts_timeout_seconds // 2)
    if not output.exists() or not output.stat().st_size:
        raise RuntimeError("Rendered clip is empty.")
    return output
