"""Public in-process source API for DataService."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.source.contracts import (
    SourceBibliographyCreateCommand,
    SourceBibliographyProjection,
    SourceCitationUsageCreateCommand,
    SourceCitationUsageProjection,
    SourceCreateCommand,
    SourceEvidencePackCreateCommand,
    SourceEvidencePackProjection,
    SourceExternalIdCreateCommand,
    SourceImportCommand,
    SourceImportProjection,
    SourceProjection,
    SourceUpdateCommand,
)
from src.dataservice.domains.source.service import SourceDataDomainService


class SourceDataService:
    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.db = session
        self._domain = SourceDataDomainService(session, autocommit=autocommit)

    async def create_source(self, command: SourceCreateCommand) -> SourceProjection:
        return await self._domain.create_source(command)

    async def upsert_source(self, command: SourceCreateCommand) -> SourceProjection:
        return await self._domain.upsert_source(command)

    async def import_source(self, command: SourceImportCommand) -> SourceImportProjection:
        return await self._domain.import_source(command)

    async def get_source(self, source_id: str) -> SourceProjection | None:
        return await self._domain.get_source(source_id)

    async def get_source_for_workspace(
        self,
        *,
        workspace_id: str,
        source_id: str,
        include_deleted: bool = False,
    ) -> SourceProjection | None:
        return await self._domain.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
            include_deleted=include_deleted,
        )

    async def get_source_detail(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> dict[str, object] | None:
        return await self._domain.get_source_detail(
            workspace_id=workspace_id,
            source_id=source_id,
        )

    async def upsert_source_external_ids(
        self,
        *,
        workspace_id: str,
        source_id: str,
        external_ids: list[SourceExternalIdCreateCommand],
    ) -> list[dict[str, object]]:
        return await self._domain.upsert_source_external_ids(
            workspace_id=workspace_id,
            source_id=source_id,
            external_ids=external_ids,
        )

    async def list_source_external_ids(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> list[dict[str, object]]:
        return await self._domain.list_source_external_ids(
            workspace_id=workspace_id,
            source_id=source_id,
        )

    async def link_source_asset(
        self,
        *,
        workspace_id: str,
        source_id: str,
        workspace_asset_id: str,
        asset_type: str,
        source_asset_id: str | None = None,
        preprocess_status: str = "skipped",
        manifest_asset_id: str | None = None,
        metadata_json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return await self._domain.link_source_asset(
            workspace_id=workspace_id,
            source_id=source_id,
            workspace_asset_id=workspace_asset_id,
            asset_type=asset_type,
            source_asset_id=source_asset_id,
            preprocess_status=preprocess_status,
            manifest_asset_id=manifest_asset_id,
            metadata_json=metadata_json,
        )

    async def build_bibliography(
        self,
        command: SourceBibliographyCreateCommand,
    ) -> SourceBibliographyProjection:
        return await self._domain.build_bibliography(command)

    async def mark_deleted(self, source_id: str) -> SourceProjection | None:
        return await self._domain.mark_deleted(source_id)

    async def mark_deleted_for_workspace(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> bool:
        return await self._domain.mark_deleted_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
        )

    async def update_source(
        self,
        *,
        workspace_id: str,
        source_id: str,
        command: SourceUpdateCommand,
    ) -> SourceProjection | None:
        return await self._domain.update_source(
            workspace_id=workspace_id,
            source_id=source_id,
            command=command,
        )

    async def mark_status(
        self,
        *,
        workspace_id: str,
        source_id: str,
        library_status: str | None = None,
        read_status: str | None = None,
    ) -> SourceProjection | None:
        return await self._domain.mark_status(
            workspace_id=workspace_id,
            source_id=source_id,
            library_status=library_status,
            read_status=read_status,
        )

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SourceProjection]:
        return await self._domain.list_sources(
            workspace_id=workspace_id,
            library_status=library_status,
            source_kind=source_kind,
            ingest_kind=ingest_kind,
            query=query,
            include_deleted=include_deleted,
            include_excluded=include_excluded,
            offset=offset,
            limit=limit,
        )

    async def list_sources_page(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, object]:
        return await self._domain.list_sources_page(
            workspace_id=workspace_id,
            library_status=library_status,
            source_kind=source_kind,
            ingest_kind=ingest_kind,
            query=query,
            offset=offset,
            limit=limit,
        )

    async def count_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        fulltext_status: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> int:
        return await self._domain.count_sources(
            workspace_id=workspace_id,
            library_status=library_status,
            source_kind=source_kind,
            ingest_kind=ingest_kind,
            query=query,
            fulltext_status=fulltext_status,
            include_deleted=include_deleted,
            include_excluded=include_excluded,
        )

    async def count_reference_summary(self, workspace_id: str) -> dict[str, int]:
        return await self._domain.count_reference_summary(workspace_id)

    async def get_library_outline(self, workspace_id: str) -> list[dict[str, object]]:
        return await self._domain.get_library_outline(workspace_id)

    async def list_source_assets(self, *, workspace_id: str, source_id: str) -> list[dict[str, object]]:
        return await self._domain.list_source_assets(workspace_id=workspace_id, source_id=source_id)

    async def get_workspace_toc_summary(self, workspace_id: str) -> str:
        return await self._domain.get_workspace_toc_summary(workspace_id)

    async def search_workspace_sections(
        self,
        workspace_id: str,
        query: str,
        *,
        limit: int = 8,
    ) -> list[dict[str, object]]:
        return await self._domain.search_workspace_sections(workspace_id, query, limit=limit)

    async def get_source_section(
        self,
        *,
        source_id: str,
        section_path: str,
        workspace_id: str,
    ) -> dict[str, object] | None:
        return await self._domain.get_source_section(
            workspace_id=workspace_id,
            source_id=source_id,
            section_path=section_path,
        )

    async def get_source_section_by_title(
        self,
        *,
        source_id: str,
        section_title: str,
        workspace_id: str,
    ) -> dict[str, object] | None:
        return await self._domain.get_source_section_by_title(
            workspace_id=workspace_id,
            source_id=source_id,
            section_title=section_title,
        )

    async def read_source_outline_node(
        self,
        *,
        workspace_id: str,
        source_id: str,
        outline_node_id: str,
    ) -> dict[str, object] | None:
        return await self._domain.read_source_outline_node(
            workspace_id=workspace_id,
            source_id=source_id,
            outline_node_id=outline_node_id,
        )

    async def read_source_pages(
        self,
        *,
        workspace_id: str,
        source_id: str,
        page_start: int,
        page_end: int,
    ) -> list[dict[str, object]]:
        return await self._domain.read_source_pages(
            workspace_id=workspace_id,
            source_id=source_id,
            page_start=page_start,
            page_end=page_end,
        )

    async def replace_source_index(
        self,
        *,
        workspace_id: str,
        source_id: str,
        outline_nodes: list[dict[str, object]],
        text_units: list[dict[str, object]],
    ) -> dict[str, int]:
        return await self._domain.replace_source_index(
            workspace_id=workspace_id,
            source_id=source_id,
            outline_nodes=outline_nodes,
            text_units=text_units,
        )

    async def search_text_units(
        self,
        *,
        workspace_id: str,
        query: str,
        source_ids: list[str] | None = None,
        limit: int = 12,
    ) -> list[dict[str, object]]:
        return await self._domain.search_text_units(
            workspace_id=workspace_id,
            query=query,
            source_ids=source_ids,
            limit=limit,
        )

    async def build_evidence_pack(
        self,
        command: SourceEvidencePackCreateCommand,
    ) -> SourceEvidencePackProjection:
        return await self._domain.build_evidence_pack(command)

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
