from fastapi import Depends, HTTPException, status
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.user_schema import UserCreate, UserResponse
from app.services.user_service import (
    UserAlreadyExistsError,
    UserNotFoundError,
    UserService,
)


async def create_or_get_user(
    payload: UserCreate, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    service = UserService(db)
    try:
        user = await service.get_or_create(payload)
    except UserAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return UserResponse.model_validate(user)


async def get_user(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    service = UserService(db)
    try:
        user = await service.get_by_id(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return UserResponse.model_validate(user)