"""Core shared dependency factories."""

from collections.abc import AsyncGenerator, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db_session
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a request-scoped database session."""
    async with get_db_session() as session:
        yield session


async def get_dataservice_client() -> AsyncIterator[AsyncDataServiceClient]:
    """Get a request-scoped standalone DataService client."""
    async with dataservice_client() as client:
        yield client
