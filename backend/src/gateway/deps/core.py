"""Core shared dependency factories."""

from collections.abc import AsyncIterator

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client


async def get_dataservice_client() -> AsyncIterator[AsyncDataServiceClient]:
    """Get a request-scoped standalone DataService client."""
    async with dataservice_client() as client:
        yield client
