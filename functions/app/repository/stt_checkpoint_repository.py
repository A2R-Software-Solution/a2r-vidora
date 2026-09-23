"""Durable completed STT requests for resumable video jobs."""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SttCheckpointRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, video_id: uuid.UUID, first_sequence: int, audio_sha256: str) -> list[dict] | None:
        row = (await self._db.execute(text(
            "SELECT segments FROM stt_request_checkpoints "
            "WHERE video_id = :video_id AND first_sequence = :first_sequence AND audio_sha256 = :digest"
        ), {"video_id": video_id, "first_sequence": first_sequence, "digest": audio_sha256})).first()
        return row[0] if row else None

    async def save(self, video_id: uuid.UUID, first_sequence: int,
                   audio_sha256: str, segments: list[dict]) -> None:
        import json

        await self._db.execute(text(
            "INSERT INTO stt_request_checkpoints (video_id, first_sequence, audio_sha256, segments) "
            "VALUES (:video_id, :first_sequence, :digest, CAST(:segments AS jsonb)) "
            "ON CONFLICT (video_id, first_sequence) DO UPDATE "
            "SET audio_sha256 = EXCLUDED.audio_sha256, segments = EXCLUDED.segments"
        ), {"video_id": video_id, "first_sequence": first_sequence,
            "digest": audio_sha256, "segments": json.dumps(segments)})
