import uuid

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit_user
from app.deps import get_db
from app.integration.groq_client import GroqRequestError
from app.schemas.video_schema import ShortSuggestion
from app.services.short_suggestion_service import ShortSuggestionService
from app.services.video_service import VideoAccessDeniedError, VideoExpiredError, VideoNotFoundError


async def suggest_shorts(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(rate_limit_user),
    *, request: Request, response: Response,
) -> list[ShortSuggestion]:
    try:
        return await ShortSuggestionService(db).suggest(video_id, user_id=user_id)
    except VideoNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Video not found.") from exc
    except VideoExpiredError as exc:
        raise HTTPException(status_code=410, detail="Video expired.") from exc
    except VideoAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Video access denied.") from exc
    except GroqRequestError as exc:
        raise HTTPException(status_code=503, detail="Short suggestions are temporarily unavailable.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
