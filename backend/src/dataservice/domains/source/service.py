"""Source library domain facade."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.provenance.repository import ProvenanceRepository
from src.dataservice.domains.source.asset_service import SourceAssetService
from src.dataservice.domains.source.bibliography_service import SourceBibliographyService
from src.dataservice.domains.source.context import SourceDomainContext
from src.dataservice.domains.source.contracts import (
    SourceAssetUpdateCommand,
    SourceBibliographyCreateCommand,
    SourceBibliographySnapshotCreateCommand,
    SourceCitationUsageCreateCommand,
    SourceCreateCommand,
    SourceEvidencePackCreateCommand,
    SourceEvidencePackProjection,
    SourceExternalIdCreateCommand,
    SourceImportCommand,
    SourceUpdateCommand,
)
from src.dataservice.domains.source.import_service import SourceImportService
from src.dataservice.domains.source.index_service import SourceIndexService
from src.dataservice.domains.source.projection_service import SourceProjectionService
from src.dataservice.domains.source.repository import SourceRepository


class SourceDataDomainService:
    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.context = SourceDomainContext(
            session=session,
            autocommit=autocommit,
            repository=SourceRepository(session),
            provenance_repository=ProvenanceRepository(session),
        )
        self.import_service = SourceImportService(self.context)
        self.asset_service = SourceAssetService(self.context)
        self.bibliography_service = SourceBibliographyService(self.context)
        self.index_service = SourceIndexService(self.context)
        self.projection_service = SourceProjectionService(
            self.context,
            asset_service=self.asset_service,
            import_service=self.import_service,
            index_service=self.index_service,
        )

    @property
    def session(self) -> AsyncSession:
        return self.context.session

    @property
    def autocommit(self) -> bool:
        return self.context.autocommit

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        self.context.autocommit = value

    @property
    def repository(self) -> SourceRepository:
        return self.context.repository

    @repository.setter
    def repository(self, value: SourceRepository) -> None:
        self.context.repository = value

    @property
    def provenance_repository(self) -> ProvenanceRepository:
        return self.context.provenance_repository

    @provenance_repository.setter
    def provenance_repository(self, value: ProvenanceRepository) -> None:
        self.context.provenance_repository = value

    async def create_source(self, command: SourceCreateCommand):
        return await self.import_service.create_source(command)

    async def upsert_source(self, command: SourceCreateCommand):
        return await self.import_service.upsert_source(command)

    async def import_source(self, command: SourceImportCommand):
        return await self.import_service.import_source(command)

    async def get_source(self, source_id: str):
        return await self.projection_service.get_source(source_id)

    async def get_source_for_workspace(
        self,
        *,
        workspace_id: str,
        source_id: str,
        include_deleted: bool = False,
    ):
        return await self.projection_service.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
            include_deleted=include_deleted,
        )

    async def get_source_detail(self, *, workspace_id: str, source_id: str):
        return await self.projection_service.get_source_detail(workspace_id=workspace_id, source_id=source_id)

    async def upsert_source_external_ids(
        self,
        *,
        workspace_id: str,
        source_id: str,
        external_ids: list[SourceExternalIdCreateCommand],
    ):
        return await self.import_service.upsert_source_external_ids(
            workspace_id=workspace_id,
            source_id=source_id,
            external_ids=external_ids,
        )

    async def list_source_external_ids(self, *, workspace_id: str, source_id: str):
        return await self.import_service.list_source_external_ids(workspace_id=workspace_id, source_id=source_id)

    async def build_bibliography(self, command: SourceBibliographyCreateCommand):
        return await self.bibliography_service.build_bibliography(command)

    async def create_bibliography_snapshot(self, command: SourceBibliographySnapshotCreateCommand):
        return await self.bibliography_service.create_bibliography_snapshot(command)

    async def mark_deleted(self, source_id: str):
        return await self.import_service.mark_deleted(source_id)

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
    ):
        return await self.asset_service.link_source_asset(
            workspace_id=workspace_id,
            source_id=source_id,
            workspace_asset_id=workspace_asset_id,
            asset_type=asset_type,
            source_asset_id=source_asset_id,
            preprocess_status=preprocess_status,
            manifest_asset_id=manifest_asset_id,
            metadata_json=metadata_json,
        )

    async def get_source_asset(self, *, workspace_id: str, source_asset_id: str):
        return await self.asset_service.get_source_asset(
            workspace_id=workspace_id,
            source_asset_id=source_asset_id,
        )

    async def update_source_asset(
        self,
        *,
        workspace_id: str,
        source_asset_id: str,
        command: SourceAssetUpdateCommand,
    ):
        return await self.asset_service.update_source_asset(
            workspace_id=workspace_id,
            source_asset_id=source_asset_id,
            command=command,
        )

    async def mark_deleted_for_workspace(self, *, workspace_id: str, source_id: str):
        return await self.import_service.mark_deleted_for_workspace(workspace_id=workspace_id, source_id=source_id)

    async def update_source(self, *, workspace_id: str, source_id: str, command: SourceUpdateCommand):
        return await self.import_service.update_source(workspace_id=workspace_id, source_id=source_id, command=command)

    async def mark_status(
        self,
        *,
        workspace_id: str,
        source_id: str,
        library_status: str | None = None,
        read_status: str | None = None,
    ):
        return await self.import_service.mark_status(
            workspace_id=workspace_id,
            source_id=source_id,
            library_status=library_status,
            read_status=read_status,
        )

    async def list_sources(self, **kwargs):
        return await self.projection_service.list_sources(**kwargs)

    async def list_sources_page(self, **kwargs):
        return await self.projection_service.list_sources_page(**kwargs)

    async def count_sources(self, **kwargs):
        return await self.projection_service.count_sources(**kwargs)

    async def count_reference_summary(self, workspace_id: str):
        return await self.projection_service.count_reference_summary(workspace_id)

    async def get_library_outline(self, workspace_id: str):
        return await self.projection_service.get_library_outline(workspace_id)

    async def get_workspace_toc_summary(self, workspace_id: str):
        return await self.projection_service.get_workspace_toc_summary(workspace_id)

    async def list_source_assets(self, *, workspace_id: str, source_id: str):
        return await self.asset_service.list_source_assets(workspace_id=workspace_id, source_id=source_id)

    async def get_source_outline(self, workspace_id: str, source_id: str, *, limit: int = 200):
        return await self.index_service.get_source_outline(workspace_id, source_id, limit=limit)

    async def search_text_units(self, **kwargs):
        return await self.index_service.search_text_units(**kwargs)

    async def build_evidence_pack(self, command: SourceEvidencePackCreateCommand) -> SourceEvidencePackProjection:
        outline = await self.projection_service.get_library_outline(command.workspace_id)
        query = command.query.strip() if command.query else None
        selected_units = (
            await self.index_service.search_text_units(
                workspace_id=command.workspace_id,
                query=query,
                source_ids=command.source_ids,
                limit=command.max_units,
            )
            if query
            else []
        )
        return SourceEvidencePackProjection(
            workspace_id=command.workspace_id,
            query=query,
            library_outline=outline,
            selected_units=selected_units,
        )

    async def search_workspace_sections(self, workspace_id: str, query: str, *, limit: int = 8):
        return await self.index_service.search_workspace_sections(workspace_id, query, limit=limit)

    async def get_source_section(self, **kwargs):
        return await self.index_service.get_source_section(**kwargs)

    async def get_source_section_by_title(self, **kwargs):
        return await self.index_service.get_source_section_by_title(**kwargs)

    async def read_source_outline_node(self, **kwargs):
        return await self.index_service.read_source_outline_node(**kwargs)

    async def read_source_pages(self, **kwargs):
        return await self.index_service.read_source_pages(**kwargs)

    async def replace_source_index(self, **kwargs):
        return await self.index_service.replace_source_index(**kwargs)

    async def list_sources_by_citation_keys(self, **kwargs):
        return await self.bibliography_service.list_sources_by_citation_keys(**kwargs)

    async def record_citation_usage(self, command: SourceCitationUsageCreateCommand):
        return await self.bibliography_service.record_citation_usage(command)
