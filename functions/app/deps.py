import os
import uuid

import firebase_admin
from fastapi import Depends, HTTPException, Header, status
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.repository.user_repository import UserRepository


def _ensure_firebase_initialized() -> None:
    """
    Lazily initializes firebase_admin on first use, not at import time.

    ApplicationDefault() reaches out to the GCP metadata server for
    credentials — during local `firebase deploy` source discovery
    there is no metadata server to reach, and doing this at import
    time blocks module load and trips the discovery timeout. Deferred
    to first actual auth check, which only happens on a real request.
    """
    if firebase_admin._apps:
        return
    if settings.google_credentials_path and os.path.exists(settings.google_credentials_path):
        firebase_admin.initialize_app(credentials.Certificate(settings.google_credentials_path))
    else:
        firebase_admin.initialize_app(credentials.ApplicationDefault())


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user_id(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID | None:
    if authorization is None:
        return None

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'.",
        )

    token = authorization.removeprefix("Bearer ").strip()

    _ensure_firebase_initialized()

    try:
        decoded = firebase_auth.verify_id_token(token)
    except firebase_auth.InvalidIdTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token."
        ) from exc
    except firebase_auth.ExpiredIdTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth token expired."
        ) from exc

    firebase_uid = decoded["uid"]

    repo = UserRepository(db)
    user = await repo.get_by_firebase_uid(firebase_uid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found for this Firebase user. Call /users to register first.",
        )

    return user.id


async def require_user_id(
    user_id: uuid.UUID | None = Depends(get_current_user_id),
) -> uuid.UUID:
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for this endpoint.",
        )
    return user_id