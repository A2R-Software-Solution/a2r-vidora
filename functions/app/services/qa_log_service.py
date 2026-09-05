from __future__ import annotations

from app.governance.runtime import QUALITY

import re
import uuid
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qa_log_model import QALog
from app.repository.qa_log_repository import QALogRepository
from app.services.transcript_chunk_service import TranscriptChunkService
from app.services.video_service import VideoService

EmbedFn = Callable[[str], Awaitable[list[float]]]
AnswerFn = Callable[[str, list[str]], Awaitable[str]]

_MAX_QUESTION_LEN = 2000
_NO_CONTEXT_ANSWER = "I couldn't find anything relevant to that question in this video."

# Matches timestamps like "0:45", "00:45", "1:47:30" — used to detect
# time-anchored questions ("what happened between 0:45 and 1:47?").
_TIMESTAMP_PATTERN = re.compile(r"\b(\d{1,2}(?::\d{2}){1,2})\b")


def _timestamp_to_seconds(timestamp: str) -> float:
    parts = [int(p) for p in timestamp.split(":")]
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return float(seconds)


def _format_seconds(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _extract_time_range(question: str) -> tuple[float, float] | None:
    """
    If `question` mentions two timestamps, returns (start, end) in
    seconds (sorted). Returns None if fewer/more than two timestamps
    are found — ambiguous cases fall back to normal semantic search
    rather than guessing.
    """
    matches = _TIMESTAMP_PATTERN.findall(question)
    if len(matches) != 2:
        return None

    seconds = sorted(_timestamp_to_seconds(m) for m in matches)
    return seconds[0], seconds[1]


class QALogService:
    """Business logic layer for the Ask Video question/answer flow."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = QALogRepository(db)
        self._video_service = VideoService(db)
        self._chunk_service = TranscriptChunkService(db)

    async def ask(
        self,
        video_id: uuid.UUID,
        question: str,
        *,
        user_id: uuid.UUID | None,
        embed_fn: EmbedFn,
        answer_fn: AnswerFn,
    ) -> QALog:
        """
        Full Ask Video flow:
          1. Load the video and confirm it belongs to this requester
             and is COMPLETED (not processing/failed/expired).
          2. Embed the question.
          3. Retrieve the most relevant chunks for this video only.
          4. Generate an answer from those chunks.
          5. Persist the log — only after steps 2-4 have all succeeded.

        embed_fn / answer_fn are injected rather than imported directly,
        so this method has no hard dependency on MiniLM or Groq clients
        and can be exercised in tests with fakes.
        """
        video = await self._video_service.get_for_user(video_id, user_id=user_id)
        self._video_service.ensure_ready_for_qa(video)

        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("question must not be empty or whitespace-only.")
        if len(cleaned_question) > _MAX_QUESTION_LEN:
            raise ValueError(
                f"question must not exceed {_MAX_QUESTION_LEN} characters."
            )

        time_range = _extract_time_range(cleaned_question)
        if time_range is not None:
            start_seconds, end_seconds = time_range
            relevant_chunks = await self._chunk_service.find_in_time_range(
                video_id, start_seconds, end_seconds
            )
        else:
            query_embedding = await embed_fn(cleaned_question)
            relevant_chunks = await self._chunk_service.find_relevant(
                video_id,
                query_embedding,
                cleaned_question,
                video_duration_seconds=video.duration,
            )

        if not relevant_chunks:
            QUALITY.labels("no_context").inc()
            answer = _NO_CONTEXT_ANSWER
        else:
            # Timestamps are always included in the context sent to the
            # LLM (not just for time-range questions) so it can mention
            # "when" in its answer even for ordinary semantic questions.
            context_texts = [
                f"[{_format_seconds(chunk.start_time)}-{_format_seconds(chunk.end_time)}] "
                f"{chunk.chunk_text}"
                for chunk in relevant_chunks
            ]
            answer = await answer_fn(cleaned_question, context_texts)

        log = await self._repo.create(
            video_id=video_id,
            user_id=user_id,
            question=cleaned_question,
            answer=answer,
        )
        await self._db.commit()
        # Response-only evidence: do not reconstruct historical sources from a new search.
        log.sources = [
            {"text": chunk.chunk_text, "start_time": chunk.start_time, "end_time": chunk.end_time}
            for chunk in relevant_chunks
        ]
        return log

    async def list_for_video(
        self,
        video_id: uuid.UUID,
        *,
        requesting_user_id: uuid.UUID | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[QALog], int]:
        """
        Backs the single GET endpoint for Q&A history. Results are
        always scoped to the requesting user's own logs — there is no
        route that returns another user's logs (see access control
        table in the test plan, section 10).
        """
        return await self._repo.list_by_video(
            video_id,
            user_id=requesting_user_id,
            search=search,
            limit=limit,
            offset=offset,
        )