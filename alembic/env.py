from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

# Import Base and all models so Alembic can detect schema changes
from app.models.base import Base
import app.models  # noqa: F401 — registers all ORM classes on Base.metadata

from app.core.config import settings

# Alembic Config object from alembic.ini
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata autogenerate compares against
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations without a live DB connection (generates SQL only).

    Useful for generating a migration script without needing the database up.
    """
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Configure the migration context and run all pending migrations."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Run migrations with a live async connection.

    Also ensures the pgvector extension is present before any migration runs —
    this is safe to call repeatedly because of IF NOT EXISTS.
    """
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # Enable pgvector — required before any migration that uses vector columns
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.commit()

        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
