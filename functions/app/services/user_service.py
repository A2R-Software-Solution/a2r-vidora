from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.user_repository import UserRepository
from app.schemas.user_schema import UserCreate


class UserAlreadyExistsError(Exception):
    """Raised when a user with the given firebase_uid or email already exists."""


class UserNotFoundError(Exception):
    """Raised when a requested user does not exist."""


class UserService:
    """Business logic layer for user account operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = UserRepository(db)

    async def get_or_create(self, payload: UserCreate):
        """
        Idempotent lookup-or-create, used right after Firebase auth
        succeeds. If a user with this firebase_uid already exists,
        that existing row is returned unchanged — this is intentionally
        not an error, since login always calls this path.
        """
        existing = await self._repo.get_by_firebase_uid(payload.firebase_uid)
        if existing is not None:
            return existing

        email_owner = await self._repo.get_by_email(payload.email)
        if email_owner is not None:
            raise UserAlreadyExistsError(
                "A different account is already registered with this email."
            )

        user = await self._repo.create(
            firebase_uid=payload.firebase_uid,
            email=payload.email,
            plan=payload.plan,
        )
        await self._db.commit()
        return user

    async def get_by_id(self, user_id: uuid.UUID):
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found.")
        return user

    async def update_plan(self, user_id: uuid.UUID, plan: str):
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found.")

        updated = await self._repo.update_plan(user, plan)
        await self._db.commit()
        return updated