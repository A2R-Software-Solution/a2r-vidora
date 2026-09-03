from fastapi import Depends, HTTPException, Query, status
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import enforce_question_rate_limit
from app.deps import get_current_user_id, get_db
from app.integration.embedding_client import embed_text
from app.integration.groq_client import generate_answer
from app.schemas.qa_logs_schema import QALogResponse, QuestionRequest
from app.services.qa_log_service import QALogService
from app.services.video_service import (
    VideoAccessDeniedError,
    VideoExpiredError,
    VideoNotFoundError,
)


async def ask_question(
    video_id: uuid.UUID,
    payload: QuestionRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(get_current_user_id),
    _rate_limit: None = Depends(enforce_question_rate_limit),
) -> QALogResponse:
    service = QALogService(db)
    try:
        log = await service.ask(
            video_id,
            payload.question,
            user_id=user_id,
            embed_fn=embed_text,
            answer_fn=generate_answer,
        )
    except VideoNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except VideoExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except VideoAccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return QALogResponse.model_validate(log)


async def list_qa_logs(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(get_current_user_id),
    search: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    service = QALogService(db)
    logs, total = await service.list_for_video(
        video_id,
        requesting_user_id=user_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [QALogResponse.model_validate(log) for log in logs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }