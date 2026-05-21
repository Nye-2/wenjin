"""Public in-process source API for DataService."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.source.contracts import (
    SourceBibliographyCreateCommand,
    SourceBibliographyProjection,
    SourceCitationUsageCreateCommand,
    SourceCitationUsageProjection,
    SourceCreateCommand,
    SourceProjection,
)
from src.dataservice.domains.source.service import SourceDataDomainService


class SourceDataService:
    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = SourceDataDomainService(session, autocommit=autocommit)

    async def create_source(self, command: SourceCreateCommand) -> SourceProjection:
        return await self._domain.create_source(command)

    async def get_source(self, source_id: str) -> SourceProjection | None:
        return await self._domain.get_source(source_id)

    async def build_bibliography(
        self,
        command: SourceBibliographyCreateCommand,
    ) -> SourceBibliographyProjection:
        return await self._domain.build_bibliography(command)

    async def mark_deleted(self, source_id: str) -> SourceProjection | None:
        return await self._domain.mark_deleted(source_id)

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

    async def list_sources_by_citation_keys(
        self,
        *,
        workspace_id: str,
        citation_keys: list[str],
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> list[SourceProjection]:
        return await self._domain.list_sources_by_citation_keys(
            workspace_id=workspace_id,
            citation_keys=citation_keys,
            include_deleted=include_deleted,
            include_excluded=include_excluded,
        )

    async def record_citation_usage(
        self,
        command: SourceCitationUsageCreateCommand,
    ) -> SourceCitationUsageProjection:
        return await self._domain.record_citation_usage(command)
