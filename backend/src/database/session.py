"""Database session and connection management."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

from .base import Base

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# Create session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


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
    ``ACADEMIAGPT_DB_AUTO_CREATE=true`` only for ephemeral local environments
    that still rely on metadata-based table creation.
    """
    async with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        if os.getenv("ACADEMIAGPT_DB_AUTO_CREATE", "").lower() in {"1", "true", "yes"}:
            logger.warning(
                "ACADEMIAGPT_DB_AUTO_CREATE is enabled; creating tables from metadata. "
                "Prefer Alembic migrations for persistent environments."
            )
            await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections.

    Should be called at application shutdown.
    """
    await engine.dispose()
