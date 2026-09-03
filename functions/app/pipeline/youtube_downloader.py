from __future__ import annotations

import asyncio
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.core.logging import logger
from app.integration import secret_manager_client

_MAX_DURATION_SECONDS = 4 * 60 * 60  # 4 hours — sane upper bound, avoids runaway jobs


class DownloadError(Exception):
    """Raised when yt-dlp fails to fetch audio or metadata for a video."""


class VideoTooLongError(Exception):
    """Raised when a video's duration exceeds the platform's processing limit."""


def _resolve_js_runtime() -> dict:
    """
    Locates the `deno` binary installed via the `deno` PyPI package on
    PATH (works the same way locally and on Cloud Run, since both
    resolve it from the active venv's bin/Scripts dir). Falls back to
    yt-dlp's own default resolution if not found on PATH, rather than
    silently disabling the JS runtime.
    """
    deno_path = shutil.which("deno")
    if deno_path:
        logger.info(f"Using deno JS runtime at: {deno_path}")
        return {"deno": {"path": deno_path}}

    logger.warning("deno binary not found on PATH; falling back to yt-dlp's default lookup")
    return {"deno": {}}


class _YtDlpLogger:
    """
    Routes yt-dlp's internal messages through our app logger instead of
    yt-dlp's default write_string(), which writes raw bytes to
    sys.stdout.buffer. Cloud Functions/Cloud Run wrap sys.stdout with a
    stream that doesn't support that raw-bytes write, which crashes with
    `TypeError: string argument expected, got 'bytes'` — this sidesteps
    that path entirely.
    """

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug] "):
            logger.debug(msg)
        else:
            logger.info(msg)

    def info(self, msg: str) -> None:
        logger.info(msg)

    def warning(self, msg: str) -> None:
        logger.warning(msg)

    def error(self, msg: str) -> None:
        logger.error(msg)


@dataclass(frozen=True)
class DownloadResult:
    audio_path: Path
    title: str | None
    duration: int | None


def _run_download(youtube_url: str, output_dir: str) -> DownloadResult:
    """Synchronous yt-dlp call — executed off the event loop by the caller."""
    output_template = str(Path(output_dir) / "%(id)s.%(ext)s")

    secret_id, cookie_content = secret_manager_client.get_youtube_cookie()
    cookie_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, dir=output_dir
    )
    try:
        cookie_file.write(cookie_content)
        cookie_file.close()

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }
            ],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": False,
            "logger": _YtDlpLogger(),
            "cookiefile": cookie_file.name,
            "js_runtimes": _resolve_js_runtime(),
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            raise DownloadError(f"yt-dlp failed for {youtube_url}: {exc}") from exc
        finally:
            # yt-dlp rewrites the cookiefile in-place if YouTube handed it
            # a refreshed session during this call. Persist that back to
            # Secret Manager so the next call (possibly a different
            # instance) starts from the newer session instead of the one
            # we started with — this is what buys extra time before a
            # full manual re-export is needed.
            refreshed_content = Path(cookie_file.name).read_text(encoding="utf-8")
            if refreshed_content != cookie_content:
                secret_manager_client.update_youtube_cookie(secret_id, refreshed_content)
    finally:
        # Cookie file holds a live session — never leave it on disk longer
        # than this call needs it.
        Path(cookie_file.name).unlink(missing_ok=True)

    duration = info.get("duration")
    if duration is not None and duration > _MAX_DURATION_SECONDS:
        raise VideoTooLongError(
            f"Video duration {duration}s exceeds the {_MAX_DURATION_SECONDS}s limit."
        )

    video_id = info["id"]
    audio_path = Path(output_dir) / f"{video_id}.mp3"
    if not audio_path.exists():
        raise DownloadError(f"Expected audio file not found at {audio_path}.")

    return DownloadResult(
        audio_path=audio_path,
        title=info.get("title"),
        duration=duration,
    )


async def download_audio(youtube_url: str, *, output_dir: str) -> DownloadResult:
    """
    Downloads best-available audio for `youtube_url` into `output_dir`
    as an mp3, and returns its path plus title/duration metadata.

    Caller owns `output_dir` lifecycle (create before, clean up after —
    see pipeline.py which uses a TemporaryDirectory context manager).
    Runs the blocking yt-dlp call in a thread executor.
    """
    logger.info(f"Downloading audio for {youtube_url}")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run_download, youtube_url, output_dir)
    logger.info(f"Downloaded audio: {result.audio_path} (duration={result.duration}s)")
    return result


def make_temp_dir() -> tempfile.TemporaryDirectory:
    """Convenience factory so pipeline.py doesn't import tempfile directly."""
    return tempfile.TemporaryDirectory(prefix="vidoraai_")