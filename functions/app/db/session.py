from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


@lru_cache
def _get_engine():
    return create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )


@lru_cache
def _get_sessionmaker():
    return async_sessionmaker(
        bind=_get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db():
    async_session = _get_sessionmaker()
    async with async_session() as session:
        yield session


class _AsyncSessionLocalProxy:
    def __call__(self):
        return _get_sessionmaker()()


AsyncSessionLocal = _AsyncSessionLocalProxy()