from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_YOUTUBE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
_ALLOWED_YOUTUBE_HOSTS = {
    "www.youtube.com",
    "youtube.com",
    "youtu.be",
    "m.youtube.com",
}


def extract_youtube_id(url: str) -> str:
    """
    Parses a YouTube watch/short URL and returns the 11-character
    video id. Raises ValueError on anything that is not a well-formed,
    https, youtube.com/youtu.be watch URL.
    """
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError("youtube_url must use https.")

    host = parsed.netloc.lower()
    if host not in _ALLOWED_YOUTUBE_HOSTS:
        raise ValueError("youtube_url must be a youtube.com or youtu.be URL.")

    if host == "youtu.be":
        video_id = parsed.path.lstrip("/")
    else:
        if parsed.path != "/watch":
            raise ValueError("youtube_url must be a /watch URL (not a playlist/channel link).")
        query = parse_qs(parsed.query)
        values = query.get("v")
        if not values:
            raise ValueError("youtube_url is missing a video id ('v' query param).")
        video_id = values[0]

    if not _YOUTUBE_ID_RE.match(video_id):
        raise ValueError("youtube_url does not contain a valid 11-character video id.")

    return video_id