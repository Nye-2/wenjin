"""Database session and connection management."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

from .base import Base

logger = logging.getLogger(__name__)


def _build_engine() -> AsyncEngine:
    """Build a fresh async engine bound to the current process."""
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def _build_session_factory(
    target_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Build a fresh session factory bound to the provided engine."""
    return async_sessionmaker(
        target_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


_engine: AsyncEngine = _build_engine()
_session_factory: async_sessionmaker[AsyncSession] = _build_session_factory(_engine)


class _AsyncEngineProxy:
    """Stable engine reference that survives process-local engine resets."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_engine(), name)

    def __repr__(self) -> str:
        return repr(get_engine())


class _AsyncSessionFactoryProxy:
    """Stable session-factory reference that follows engine resets."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return get_async_session_factory()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(get_async_session_factory(), name)

    def __repr__(self) -> str:
        return repr(get_async_session_factory())


engine = _AsyncEngineProxy()
async_session_factory = _AsyncSessionFactoryProxy()


def get_engine() -> AsyncEngine:
    """Return the current process-local async engine."""
    return _engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the current process-local async session factory."""
    return _session_factory


async def reset_db_engine(*, dispose_current: bool = True) -> None:
    """Rebuild the async engine/session factory for the current process.

    Celery forks worker child processes after module import. Reusing a parent
    process async engine in the child can leak loop-bound futures into a new
    event loop. This helper provides a clean child-process-local engine.
    """
    global _engine, _session_factory

    previous_engine = _engine
    _engine = _build_engine()
    _session_factory = _build_session_factory(_engine)

    if dispose_current:
        await previous_engine.dispose()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session as async context manager.

    Usage:
        async with get_db_session() as session:
            result = await session.execute(query)
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables.

    Initializes database prerequisites needed at application startup.

    Schema creation is intentionally delegated to Alembic migrations. Set
    ``GUANLAN_DB_AUTO_CREATE=true`` only for ephemeral local environments
    that still rely on metadata-based table creation.
    """
    async with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        if os.getenv("GUANLAN_DB_AUTO_CREATE", "").lower() in {"1", "true", "yes"}:
            logger.warning(
                "GUANLAN_DB_AUTO_CREATE is enabled; creating tables from metadata. "
                "Prefer Alembic migrations for persistent environments."
            )
            await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections.

    Should be called at application shutdown.
    """
    await engine.dispose()
