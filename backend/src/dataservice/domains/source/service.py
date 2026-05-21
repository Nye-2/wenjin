"""Source library domain service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.domains.provenance.projection import provenance_link_to_projection
from src.dataservice.domains.provenance.repository import ProvenanceRepository
from src.dataservice.domains.source.contracts import (
    SourceCitationUsageCreateCommand,
    SourceCitationUsageProjection,
    SourceCreateCommand,
    SourceProjection,
)
from src.dataservice.domains.source.projection import source_to_projection
from src.dataservice.domains.source.repository import SourceRepository

_SOURCE_USED_IN_DRAFT_STATUSES = {"candidate", "included"}


class SourceDataDomainService:
    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = SourceRepository(session)
        self.provenance_repository = ProvenanceRepository(session)

    async def create_source(self, command: SourceCreateCommand) -> SourceProjection:
        normalized_title = command.normalized_title or command.title.strip().lower()
        record = self.repository.create_source(
            {
                **command.model_dump(exclude={"normalized_title"}),
                "normalized_title": normalized_title,
            }
        )
        await self._finish()
        return source_to_projection(record)

    async def get_source(self, source_id: str) -> SourceProjection | None:
        record = await self.repository.get_source(source_id)
        return source_to_projection(record) if record else None

    async def mark_deleted(self, source_id: str) -> SourceProjection | None:
        record = await self.repository.get_source(source_id)
        if record is None:
            return None
        record.is_deleted = True
        record.updated_at = datetime.now(UTC)
        await self._finish()
        return source_to_projection(record)

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[SourceProjection]:
        return [
            source_to_projection(record)
            for record in await self.repository.list_sources(
                workspace_id=workspace_id,
                library_status=library_status,
                include_deleted=include_deleted,
                limit=limit,
            )
        ]

    async def list_sources_by_citation_keys(
        self,
        *,
        workspace_id: str,
        citation_keys: list[str],
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> list[SourceProjection]:
        unique_keys = self._normalize_citation_keys(citation_keys)
        if not workspace_id or not unique_keys:
            return []
        return [
            source_to_projection(record)
            for record in await self.repository.list_sources_by_citation_keys(
                workspace_id=workspace_id,
                citation_keys=unique_keys,
                include_deleted=include_deleted,
                include_excluded=include_excluded,
            )
        ]

    async def record_citation_usage(
        self,
        command: SourceCitationUsageCreateCommand,
    ) -> SourceCitationUsageProjection:
        unique_keys = self._normalize_citation_keys(command.citation_keys)
        if not command.workspace_id or not unique_keys:
            return SourceCitationUsageProjection(recorded=0)

        records = await self.repository.list_sources_by_citation_keys(
            workspace_id=command.workspace_id,
            citation_keys=unique_keys,
            include_deleted=False,
            include_excluded=False,
        )
        if not records:
            return SourceCitationUsageProjection(recorded=0)

        source_ids: list[str] = []
        citation_keys: list[str] = []
        provenance_link_ids: list[str] = []
        for record in records:
            source_id = str(record.id)
            citation_key = str(record.citation_key)
            if command.mark_used_in_draft and str(record.library_status) in _SOURCE_USED_IN_DRAFT_STATUSES:
                record.library_status = "used_in_draft"
                record.updated_at = datetime.now(UTC)

            target_ref_json = {
                **command.target_ref_json,
                **({"latex_project_id": command.latex_project_id} if command.latex_project_id else {}),
                **({"target_section": command.target_section} if command.target_section else {}),
                **({"artifact_id": command.artifact_id} if command.artifact_id else {}),
                **({"task_id": command.task_id} if command.task_id else {}),
                "citation_key": citation_key,
            }
            link = self.provenance_repository.create_link(
                ProvenanceLinkCreateCommand(
                    workspace_id=command.workspace_id,
                    source_id=source_id,
                    target_domain=command.target_domain,
                    target_kind=command.target_kind,
                    target_id=command.target_id,
                    target_ref_json=target_ref_json,
                    relation_kind="cited",
                    citation_key=citation_key,
                    claim_text=command.claim_text,
                    generated_text=command.generated_text,
                    execution_id=command.execution_id,
                    metadata_json={
                        "usage_type": command.usage_type,
                        "accepted_status": command.accepted_status,
                        "mark_used_in_draft": command.mark_used_in_draft,
                    },
                ).model_dump()
            )
            source_ids.append(source_id)
            citation_keys.append(citation_key)
            provenance_link_ids.append(provenance_link_to_projection(link).id)

        await self._finish()
        return SourceCitationUsageProjection(
            recorded=len(source_ids),
            source_ids=source_ids,
            citation_keys=citation_keys,
            provenance_link_ids=provenance_link_ids,
        )

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

    @staticmethod
    def _normalize_citation_keys(citation_keys: list[str]) -> list[str]:
        return [
            key
            for key in dict.fromkeys(str(item).strip() for item in citation_keys)
            if key
        ]
