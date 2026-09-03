from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_model import User


class UserRepository:
    """Encapsulates all SQL access for the `users` table."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_firebase_uid(self, firebase_uid: str) -> User | None:
        result = await self._db.execute(
            select(User).where(User.firebase_uid == firebase_uid)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, *, firebase_uid: str, email: str, plan: str) -> User:
        user = User(firebase_uid=firebase_uid, email=email, plan=plan)
        self._db.add(user)
        await self._db.flush()
        await self._db.refresh(user)
        return user

    async def update_plan(self, user: User, plan: str) -> User:
        user.plan = plan
        await self._db.flush()
        await self._db.refresh(user)
        return user