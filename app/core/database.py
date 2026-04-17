from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _build_engine() -> AsyncEngine:
    """
    Create the async SQLAlchemy engine from settings.

    When TESTING=1 is set (pytest runs), NullPool is used so every session
    creates a fresh connection and closes it immediately — no shared pool
    state between tests running on different asyncio event loops.
    """
    try:
        if os.environ.get("TESTING") == "1":
            engine = create_async_engine(
                settings.database_url,
                poolclass=NullPool,
                echo=False,
                future=True,
            )
        else:
            engine = create_async_engine(
                settings.database_url,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_timeout=settings.db_pool_timeout,
                echo=settings.app_debug,
                future=True,
            )
        log.info("database engine created", url=settings.database_url.split("@")[-1])
        return engine
    except Exception as exc:
        log.critical("failed to create database engine", error=str(exc))
        raise


engine: AsyncEngine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an AsyncSession and handles cleanup.

    Rolls back on exception so the session is never left in a dirty state.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
