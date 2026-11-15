"""Sources of the Song Merger Pro editor: one YouTube track fetched once for
its waveform and preview, then reused by the merge. Loading a source costs no
credits, so each owner is limited to a number of new sources per hour."""
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import delete, select
from app.core.config import settings
from app.integration import audio_merge_storage
from app.middleware.logging import logger
from app.models.audio_merge_model import AudioSource
from app.pipeline.audio_source_worker import ACTIVE_STATUSES, stall_window
from app.services.credit_service import CreditOwner
from app.utils.youtube import extract_youtube_id

# A source this close to expiry is not handed out again; a fresh one is prepared.
REUSE_MARGIN = timedelta(minutes=20)


class AudioSourceService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _mine(owner: CreditOwner):
        return AudioSource.user_id == owner.user_id if owner.user_id else AudioSource.guest_key == owner.guest_key

    @staticmethod
    def _expire_stalled(sources):
        cutoff = datetime.now(timezone.utc) - stall_window()
        for source in sources:
            if source.status in ACTIVE_STATUSES and source.updated_at < cutoff:
                source.status, source.error_code = "failed", "TIMED_OUT"

    async def create(self, url: str, owner: CreditOwner) -> tuple[AudioSource, bool]:
        """Returns (source, created). The caller starts the work only for a new
        source; a track this owner already loaded is handed back as it is."""
        video_id = extract_youtube_id(url)
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        mine = list((await self.db.execute(
            select(AudioSource).where(self._mine(owner), (AudioSource.expires_at > now) | (AudioSource.created_at > hour_ago))
            .order_by(AudioSource.created_at.desc()))).scalars())
        self._expire_stalled(mine)
        existing = next((s for s in mine if s.video_id == video_id and s.status != "failed"
                         and s.expires_at > now + REUSE_MARGIN), None)
        if existing is not None:
            await self.db.commit()
            return existing, False
        if sum(s.created_at > hour_ago for s in mine) >= settings.audio_merge_sources_per_hour:
            await self.db.commit()
            raise HTTPException(429, "You have loaded a lot of songs in the last hour. Please wait a little before loading more.")
        source = AudioSource(
            id=uuid.uuid4(), user_id=owner.user_id, guest_key=owner.guest_key, video_id=video_id, url=url,
            status="queued", created_at=now, updated_at=now,
            expires_at=now + timedelta(minutes=settings.audio_merge_source_retention_minutes))
        self.db.add(source)
        await self.db.commit()
        return source, True

    async def get(self, source_id: uuid.UUID, owner: CreditOwner) -> AudioSource:
        source = (await self.db.execute(
            select(AudioSource).where(AudioSource.id == source_id, self._mine(owner)))).scalar_one_or_none()
        if source is None:
            raise HTTPException(404, "Song not found.")
        self._expire_stalled([source])
        await self.db.commit()
        return source

    async def mark_failed(self, source: AudioSource, code: str) -> None:
        source.status, source.error_code = "failed", code
        await self.db.commit()

    async def describe(self, source: AudioSource) -> dict:
        """What the editor needs. Storage names stay private; the preview is a signed link."""
        now = datetime.now(timezone.utc)
        ready = source.status == "ready" and source.expires_at > now and source.preview_object
        preview_url = None
        if ready:
            valid_for = max(60, min(6 * 3600, int((source.expires_at - now).total_seconds())))
            preview_url = await audio_merge_storage.signed_preview_url(source.preview_object, valid_for)
        return {
            "id": source.id, "video_id": source.video_id, "url": source.url, "title": source.title,
            "status": "expired" if source.expires_at <= now else source.status,
            "error_code": source.error_code, "duration_seconds": source.duration_seconds,
            "peaks": source.peaks if ready else None, "preview_url": preview_url,
            "expires_at": source.expires_at,
        }

    async def originals(self, wanted: dict[uuid.UUID, str], owner: CreditOwner) -> dict[uuid.UUID, str]:
        """wanted: {source id: video id the track claims}. Returns the stored
        original audio of every source that is this owner's, ready and matching."""
        if not wanted:
            return {}
        now = datetime.now(timezone.utc)
        rows = (await self.db.execute(select(AudioSource).where(
            AudioSource.id.in_(list(wanted)), self._mine(owner), AudioSource.status == "ready",
            AudioSource.expires_at > now))).scalars()
        return {s.id: s.original_object for s in rows if s.original_object and s.video_id == wanted[s.id]}

    async def purge_expired(self, *, now: datetime | None = None) -> int:
        """Deletes expired sources and their stored audio, except ones a worker may still be writing."""
        now = now or datetime.now(timezone.utc)
        sources = list((await self.db.execute(
            select(AudioSource).where(AudioSource.expires_at <= now).with_for_update())).scalars())
        purgeable = [s for s in sources if s.status not in ACTIVE_STATUSES or s.updated_at < now - stall_window()]
        for source in purgeable:
            for name in (source.preview_object, source.original_object):
                if not name:
                    continue
                try:
                    await audio_merge_storage.delete(name)
                except Exception:
                    logger.exception("audio_source_object_delete_failed object=%s", name)
        if purgeable:
            await self.db.execute(delete(AudioSource).where(AudioSource.id.in_([s.id for s in purgeable])))
        await self.db.commit()
        logger.info("Purged %s expired audio sources", len(purgeable))
        return len(purgeable)
