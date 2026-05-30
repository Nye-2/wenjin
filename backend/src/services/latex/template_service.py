"""Template catalog access for LaTeX projects."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client


class LatexTemplateService:
    """Service for template catalog initialization and listing."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def ensure_defaults(self) -> None:
        async with self._client() as client:
            await client.ensure_default_latex_templates()

    async def list_templates(self) -> list[object]:
        async with self._client() as client:
            return await client.list_latex_templates()
