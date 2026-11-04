"""Media Downloader catalogue: the qualities a user can pick, what each costs
per started minute, and the yt-dlp format selection behind it. Pure rules, no I/O."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaQuality:
    code: str
    kind: str  # "audio" | "video"
    label: str
    credits_per_minute: int
    bitrate_kbps: int | None = None  # audio only
    height: int | None = None  # video only
    # Listed (priced, shown as "coming soon") but not downloadable yet.
    available: bool = True

    @property
    def extension(self) -> str:
        return "mp3" if self.kind == "audio" else "mp4"


QUALITIES: dict[str, MediaQuality] = {q.code: q for q in (
    MediaQuality("mp3_48", "audio", "MP3 48 kbps", 1, bitrate_kbps=48),
    MediaQuality("mp3_128", "audio", "MP3 128 kbps", 1, bitrate_kbps=128),
    MediaQuality("mp3_256", "audio", "MP3 256 kbps", 2, bitrate_kbps=256),
    MediaQuality("mp4_144", "video", "MP4 144p", 1, height=144),
    MediaQuality("mp4_240", "video", "MP4 240p", 1, height=240),
    MediaQuality("mp4_360", "video", "MP4 360p", 1, height=360),
    MediaQuality("mp4_480", "video", "MP4 480p", 2, height=480),
    MediaQuality("mp4_720", "video", "MP4 720p", 3, height=720),
    # Off for now: the largest files, and the worker keeps them in memory-backed /tmp.
    MediaQuality("mp4_1080", "video", "MP4 1080p", 4, height=1080, available=False),
)}


def get_quality(code: str) -> MediaQuality:
    quality = QUALITIES.get(code)
    if quality is None:
        raise ValueError(f"Unknown quality: {code}")
    return quality


def media_credit_cost(quality: MediaQuality, duration_seconds: int) -> int:
    """Every started minute costs the quality's rate; a non-empty file costs at least one minute."""
    if duration_seconds <= 0:
        raise ValueError("Media duration must be positive.")
    return math.ceil(duration_seconds / 60) * quality.credits_per_minute


def ytdlp_format(quality: MediaQuality) -> str:
    """Format selector. Video merges the best stream at or below the height into MP4."""
    if quality.kind == "audio":
        return "bestaudio/best"
    h = quality.height
    return (f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={h}][ext=mp4]/best[height<={h}]")
