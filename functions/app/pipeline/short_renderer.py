"""Bounded subprocesses and temporary files for 720x1280 captioned MP4 clips."""
import os
import re
import shutil
import subprocess
from pathlib import Path
from app.core.config import settings
from app.integration import secret_manager_client


def _run(args, directory, timeout):
    process = subprocess.Popen(args, cwd=directory, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=os.name != "nt")
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
        raise RuntimeError("Media operation timed out.") from None
    if code:
        raise RuntimeError("Media operation failed.")


def _srt_time(seconds):
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def caption_text(chunks, start, end):
    """Approximate phrase timings from transcript chunks; word timings aren't retained."""
    cues = []
    previous_end = 0.0
    for chunk in chunks:
        words = re.sub(r"[<>\{\}\\]", "", chunk.chunk_text).split()
        if not words or chunk.end_time <= chunk.start_time:
            continue
        for index in range(0, len(words), 8):
            left = chunk.start_time + (chunk.end_time - chunk.start_time) * index / len(words)
            right = chunk.start_time + (chunk.end_time - chunk.start_time) * min(index + 8, len(words)) / len(words)
            left, right = max(left, start) - start, min(right, end) - start
            left = max(left, previous_end)
            if right <= left:
                continue
            cues.append(f"{len(cues) + 1}\n{_srt_time(left)} --> {_srt_time(right)}\n{' '.join(words[index:index + 8])}\n")
            previous_end = right
    return "\n".join(cues)


def render_short(url, start, end, chunks, directory):
    import sys
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required.")
    directory = Path(directory)
    captions = caption_text(chunks, start, end)
    if not captions:
        raise ValueError("No captions available for this range.")
    (directory / "captions.srt").write_text(captions, encoding="utf-8")
    secret_id, cookies = secret_manager_client.get_youtube_cookie()
    cookie_path = directory / "cookies.txt"
    cookie_path.write_text(cookies, encoding="utf-8")
    try:
        # Fetch only the requested section, not a multi-hour source video.
        _run([sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-warnings",
              "--cookies", str(cookie_path), "--js-runtimes", "deno",
              "--socket-timeout", str(settings.download_timeout_seconds),
              "--retries", str(settings.download_retries),
              "--download-sections", f"*{start}-{end}", "--force-keyframes-at-cuts",
              "-f", "bv*[height<=720]+ba/b[height<=720]", "--merge-output-format", "mp4",
              "-o", "source.%(ext)s", url], directory, settings.shorts_timeout_seconds // 2)
        refreshed = cookie_path.read_text(encoding="utf-8")
        if refreshed != cookies:
            secret_manager_client.update_youtube_cookie(secret_id, refreshed)
    finally:
        cookie_path.unlink(missing_ok=True)
    sources = [p for p in directory.glob("source.*") if p.suffix in {".mp4", ".webm", ".mkv"}]
    if len(sources) != 1:
        raise RuntimeError("Source clip is unavailable.")
    return render_local(sources[0], end - start, directory, ffmpeg)


def render_local(source, duration, directory, ffmpeg=None):
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    output = Path(directory) / "short.mp4"
    filters = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=20:2[back];"
        "[fg]scale=720:1280:force_original_aspect_ratio=decrease[front];"
        "[back][front]overlay=(W-w)/2:(H-h)/2,setsar=1,"
        "subtitles=captions.srt:force_style='FontName=DejaVu Sans,FontSize=20,"
        "Outline=2,Alignment=2,MarginV=65'[out]"
    )
    _run([ffmpeg, "-y", "-v", "error", "-i", str(Path(source).resolve()),
          "-filter_complex", filters, "-map", "[out]", "-map", "0:a:0?",
          "-t", str(duration), "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "24", "-pix_fmt", "yuv420p", "-threads", "2", "-filter_complex_threads", "1",
          "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output.resolve())],
         directory, settings.shorts_timeout_seconds // 2)
    if not output.exists() or not output.stat().st_size:
        raise RuntimeError("Rendered clip is empty.")
    return output
