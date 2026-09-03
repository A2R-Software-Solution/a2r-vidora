from __future__ import annotations

import random
import time
from dataclasses import dataclass

from google.cloud import secretmanager

from app.core.config import settings
from app.core.logging import logger

_CACHE_TTL_SECONDS = 30 * 60  # 30 min — cookies don't change often; avoids a Secret Manager call every request


@dataclass
class _CacheEntry:
    content: str
    fetched_at: float


_cache: dict[str, _CacheEntry] = {}
_client: secretmanager.SecretManagerServiceClient | None = None


def _get_client() -> secretmanager.SecretManagerServiceClient:
    global _client
    if _client is None:
        _client = secretmanager.SecretManagerServiceClient()
    return _client


def _fetch_secret(secret_id: str) -> str:
    """Fetches the 'latest' version of a secret's payload as text."""
    name = f"projects/{settings.gcp_project_id}/secrets/{secret_id}/versions/latest"
    response = _get_client().access_secret_version(name=name)
    return response.payload.data.decode("utf-8")


def _get_cached_secret(secret_id: str) -> str:
    cached = _cache.get(secret_id)
    now = time.time()

    if cached is not None and (now - cached.fetched_at) < _CACHE_TTL_SECONDS:
        return cached.content

    logger.info(f"Fetching secret from Secret Manager: {secret_id}")
    content = _fetch_secret(secret_id)
    _cache[secret_id] = _CacheEntry(content=content, fetched_at=now)
    return content


def get_youtube_cookie() -> tuple[str, str]:
    """
    Returns (secret_id, cookie_content) for one of the configured
    YouTube accounts, chosen at random per call. Content is cached
    in-memory per secret_id for _CACHE_TTL_SECONDS to avoid a Secret
    Manager round-trip on every download.

    Callers that pass the cookiefile to yt-dlp should hang onto
    secret_id and pass it to update_youtube_cookie() afterwards, so
    any session refresh yt-dlp wrote to the file gets persisted back.
    """
    secret_id = random.choice(settings.youtube_cookie_secret_ids)
    return secret_id, _get_cached_secret(secret_id)


def update_youtube_cookie(secret_id: str, new_content: str) -> None:
    """
    Adds a new Secret Manager version for `secret_id` with the given
    cookie content, and updates the in-memory cache to match — so a
    session refresh yt-dlp performs mid-download doesn't just live in
    a local temp file that gets deleted, but gets persisted for the
    next call too. Best-effort: logs and swallows failures rather than
    breaking the pipeline over a refresh-persistence issue.
    """
    try:
        parent = f"projects/{settings.gcp_project_id}/secrets/{secret_id}"
        _get_client().add_secret_version(
            parent=parent, payload={"data": new_content.encode("utf-8")}
        )
        _cache[secret_id] = _CacheEntry(content=new_content, fetched_at=time.time())
        logger.info(f"Persisted refreshed cookies for {secret_id}")
    except Exception as exc:  # noqa: BLE001 — never let a refresh-save failure break the pipeline
        logger.warning(f"Failed to persist refreshed cookies for {secret_id}: {exc}")