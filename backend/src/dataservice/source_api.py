"""Public in-process source API for DataService."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.source.contracts import SourceCreateCommand, SourceProjection
from src.dataservice.domains.source.service import SourceDataDomainService


class SourceDataService:
    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = SourceDataDomainService(session, autocommit=autocommit)

    async def create_source(self, command: SourceCreateCommand) -> SourceProjection:
        return await self._domain.create_source(command)

    async def get_source(self, source_id: str) -> SourceProjection | None:
        return await self._domain.get_source(source_id)

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[SourceProjection]:
        return await self._domain.list_sources(
            workspace_id=workspace_id,
            library_status=library_status,
            include_deleted=include_deleted,
            limit=limit,
        )
