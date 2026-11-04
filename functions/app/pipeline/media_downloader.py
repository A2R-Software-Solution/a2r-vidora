"""yt-dlp calls for the Media Downloader: a metadata probe (for the preview and
price) and the actual audio or video download in the chosen quality."""
from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.core.config import settings
from app.middleware.logging import logger
from app.pipeline.media_formats import MediaQuality, ytdlp_format
from app.pipeline.youtube_downloader import (
    DownloadError,
    UnsupportedVideoError,
    VideoTooLongError,
    YouTubeBotChallengeError,
    _YtDlpLogger,
    _cookie_file,
    _resolve_js_runtime,
    is_youtube_bot_challenge,
)


@dataclass(frozen=True)
class MediaInfo:
    video_id: str
    title: str | None
    duration: int
    thumbnail: str | None


@dataclass(frozen=True)
class MediaFile:
    path: Path
    title: str | None


def _base_options(cookiefile: str, output_dir: str) -> dict:
    return {
        "outtmpl": str(Path(output_dir) / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "logger": _YtDlpLogger(),
        "cookiefile": cookiefile,
        "js_runtimes": _resolve_js_runtime(),
        "socket_timeout": settings.download_timeout_seconds,
        "retries": settings.download_retries,
        "fragment_retries": settings.download_retries,
    }


def _to_download_error(url: str, exc: yt_dlp.utils.DownloadError) -> Exception:
    if is_youtube_bot_challenge(str(exc)):
        return YouTubeBotChallengeError("YouTube session temporarily unavailable.")
    return DownloadError(f"yt-dlp failed for {url}: {exc}")


def _check_media(info: dict | None, max_seconds: int) -> MediaInfo:
    if not info:
        raise DownloadError("yt-dlp returned no media metadata.")
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
        raise UnsupportedVideoError("Live and upcoming streams are not supported.")
    duration = info.get("duration")
    if duration is None:
        raise UnsupportedVideoError("Media duration is unavailable.")
    if duration > max_seconds:
        raise VideoTooLongError(f"Media duration {duration}s exceeds the {max_seconds}s limit.")
    return MediaInfo(
        video_id=info["id"],
        title=info.get("title"),
        duration=int(duration),
        thumbnail=info.get("thumbnail"),
    )


def _run_probe(url: str, max_seconds: int) -> MediaInfo:
    with tempfile.TemporaryDirectory(prefix="vidora_probe_") as output_dir:
        with _cookie_file(output_dir) as cookiefile:
            try:
                with yt_dlp.YoutubeDL(_base_options(cookiefile, output_dir)) as ydl:
                    info = ydl.extract_info(url, download=False)
            except yt_dlp.utils.DownloadError as exc:
                raise _to_download_error(url, exc) from exc
    return _check_media(info, max_seconds)


def _run_download(url: str, output_dir: str, quality: MediaQuality, max_seconds: int) -> MediaFile:
    with _cookie_file(output_dir) as cookiefile:
        options = _base_options(cookiefile, output_dir) | {"format": ytdlp_format(quality)}
        if quality.kind == "audio":
            options["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(quality.bitrate_kbps),
            }]
        else:
            options["merge_output_format"] = "mp4"
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                # Re-check the length here: the price was set from an earlier probe.
                media = _check_media(ydl.extract_info(url, download=False), max_seconds)
                ydl.download([url])
        except yt_dlp.utils.DownloadError as exc:
            raise _to_download_error(url, exc) from exc

    path = Path(output_dir) / f"{media.video_id}.{quality.extension}"
    if not path.exists():
        raise DownloadError(f"Expected media file not found at {path}.")
    return MediaFile(path=path, title=media.title)


async def probe_media(url: str, *, max_seconds: int | None = None) -> MediaInfo:
    """Title, length and thumbnail for a YouTube link, without downloading anything."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_probe, url, max_seconds or settings.media_download_max_seconds)


async def download_media(url: str, *, output_dir: str, quality: MediaQuality,
                         max_seconds: int | None = None) -> MediaFile:
    """Downloads `url` in `quality` into `output_dir`. The caller owns that directory."""
    logger.info(f"Downloading media {quality.code} for {url}")
    loop = asyncio.get_running_loop()
    limit = max_seconds or settings.media_download_max_seconds
    return await loop.run_in_executor(None, _run_download, url, output_dir, quality, limit)
