"""Core shared dependency factories."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a request-scoped database session."""
    async with get_db_session() as session:
        yield session
