from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.integration.groq_client import generate_short_suggestions
from app.schemas.video_schema import ShortSuggestion
from app.services.transcript_chunk_service import TranscriptChunkService
from app.services.video_service import VideoService


class ShortSuggestionService:
    """Phase 1: transcript-based ideas only. No source video is downloaded or rendered."""

    def __init__(self, db: AsyncSession) -> None:
        self._video_service = VideoService(db)
        self._chunk_service = TranscriptChunkService(db)

    async def suggest(self, video_id: uuid.UUID, *, user_id: uuid.UUID | None) -> list[ShortSuggestion]:
        video = await self._video_service.get_for_user(video_id, user_id=user_id)
        self._video_service.ensure_ready_for_qa(video)
        chunks = await self._chunk_service.list_for_video(video_id)
        transcript = "\n".join(
            f"[{int(chunk.start_time)}-{int(chunk.end_time)}] {chunk.chunk_text}"
            for chunk in chunks
        )
        raw_suggestions = await generate_short_suggestions(transcript)
        suggestions: list[ShortSuggestion] = []
        for item in raw_suggestions:
            try:
                suggestion = ShortSuggestion.model_validate(item)
            except ValueError:
                continue
            if suggestion.end_time > (video.duration or 0):
                continue
            if not 20 <= suggestion.end_time - suggestion.start_time <= 60:
                continue
            suggestions.append(suggestion)
        if not suggestions:
            raise ValueError("We couldn't find suitable 20-60 second clips in this video.")
        return suggestions[:2]
