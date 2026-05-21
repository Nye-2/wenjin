"""Runtime provider for standalone DataService HTTP clients."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.dataservice_client import AsyncDataServiceClient


@asynccontextmanager
async def dataservice_client() -> AsyncIterator[AsyncDataServiceClient]:
    async with AsyncDataServiceClient() as client:
        yield client
