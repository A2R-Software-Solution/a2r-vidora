import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qa_log_model import QALog


class QALogRepository:
    """Encapsulates all SQL access for the `qa_logs` table."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, log_id: uuid.UUID) -> QALog | None:
        result = await self._db.execute(select(QALog).where(QALog.id == log_id))
        return result.scalar_one_or_none()

    async def delete_by_video(self, video_id: uuid.UUID) -> None:
        await self._db.execute(sa_delete(QALog).where(QALog.video_id == video_id))
        await self._db.flush()

    async def create(
        self,
        *,
        video_id: uuid.UUID,
        user_id: uuid.UUID | None,
        question: str,
        answer: str,
    ) -> QALog:
        log = QALog(
            video_id=video_id,
            user_id=user_id,
            question=question,
            answer=answer,
        )
        self._db.add(log)
        await self._db.flush()
        await self._db.refresh(log)
        return log

    async def list_by_video(
        self,
        video_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[QALog], int]:
        """
        Search + pagination for a single video's Q&A history.

        user_id: when provided, scopes results to that user's own logs
                 (ownership check is the caller's responsibility to decide
                 when this filter applies — see module docstring).
        search:  case-insensitive substring match against question text.
        Returns (rows, total_count) so the caller can build a paginated
        response without a second round trip.
        """
        base_query = select(QALog).where(QALog.video_id == video_id)
        count_query = select(func.count()).select_from(QALog).where(
            QALog.video_id == video_id
        )

        if user_id is not None:
            base_query = base_query.where(QALog.user_id == user_id)
            count_query = count_query.where(QALog.user_id == user_id)

        if search:
            pattern = f"%{search}%"
            base_query = base_query.where(QALog.question.ilike(pattern))
            count_query = count_query.where(QALog.question.ilike(pattern))

        base_query = (
            base_query.order_by(QALog.created_at.desc()).limit(limit).offset(offset)
        )

        rows_result = await self._db.execute(base_query)
        count_result = await self._db.execute(count_query)

        rows = list(rows_result.scalars().all())
        total = count_result.scalar_one()

        return rows, total