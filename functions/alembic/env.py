import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Load environment variables from functions/.env
load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import your SQLAlchemy Base here later
# from app.db.base import Base
# target_metadata = Base.metadata

from app.db.base import Base
from app.models import User, Video, TranscriptChunk, QALog # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    url = os.getenv("DATABASE_URL")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run migrations using an active connection."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in online mode using AsyncEngine."""

    database_url = os.getenv("DATABASE_URL")

    connectable = async_engine_from_config(
    {
        "sqlalchemy.url": database_url,
    },
    prefix="sqlalchemy.",
    poolclass=pool.NullPool,
    connect_args={"statement_cache_size": 0},
)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())