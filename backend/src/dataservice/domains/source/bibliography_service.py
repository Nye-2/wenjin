"""Source bibliography and citation usage service."""

from __future__ import annotations

from datetime import UTC, datetime

from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.domains.provenance.projection import provenance_link_to_projection
from src.dataservice.domains.source.context import SourceDomainContext
from src.dataservice.domains.source.contracts import (
    SourceBibliographyCreateCommand,
    SourceBibliographyProjection,
    SourceBibliographySnapshotCreateCommand,
    SourceBibliographySnapshotProjection,
    SourceCitationUsageCreateCommand,
    SourceCitationUsageProjection,
    SourceProjection,
)
from src.dataservice.domains.source.helpers import (
    format_bibtex_entry,
    normalize_citation_keys,
    normalize_ids,
)
from src.dataservice.domains.source.projection import (
    source_bibtex_snapshot_to_projection,
    source_to_projection,
)

_SOURCE_USED_IN_DRAFT_STATUSES = {"candidate", "included"}


class SourceBibliographyService:
    def __init__(self, context: SourceDomainContext) -> None:
        self.context = context

    async def build_bibliography(
        self,
        command: SourceBibliographyCreateCommand,
    ) -> SourceBibliographyProjection:
        unique_ids = normalize_ids(command.source_ids)
        if not command.workspace_id or not unique_ids:
            return SourceBibliographyProjection()

        records = await self.context.repository.list_sources_by_ids(
            workspace_id=command.workspace_id,
            source_ids=unique_ids,
            include_deleted=command.include_deleted,
            include_excluded=command.include_excluded,
        )
        by_id = {str(record.id): record for record in records}
        ordered_records = [by_id[source_id] for source_id in unique_ids if source_id in by_id]
        if not ordered_records:
            return SourceBibliographyProjection()

        return SourceBibliographyProjection(
            content="\n\n".join(format_bibtex_entry(record) for record in ordered_records),
            count=len(ordered_records),
            source_ids=[str(record.id) for record in ordered_records],
            citation_keys=[str(record.citation_key) for record in ordered_records],
        )

    async def create_bibliography_snapshot(
        self,
        command: SourceBibliographySnapshotCreateCommand,
    ) -> SourceBibliographySnapshotProjection:
        record = self.context.repository.create_bibtex_snapshot(command.model_dump())
        await self.context.finish()
        return source_bibtex_snapshot_to_projection(record)

    async def list_sources_by_citation_keys(
        self,
        *,
        workspace_id: str,
        citation_keys: list[str],
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> list[SourceProjection]:
        unique_keys = normalize_citation_keys(citation_keys)
        if not workspace_id or not unique_keys:
            return []
        return [
            source_to_projection(record)
            for record in await self.context.repository.list_sources_by_citation_keys(
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
        unique_keys = normalize_citation_keys(command.citation_keys)
        if not command.workspace_id or not unique_keys:
            return SourceCitationUsageProjection(recorded=0)

        records = await self.context.repository.list_sources_by_citation_keys(
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
            link = self.context.provenance_repository.create_link(
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

        await self.context.finish()
        return SourceCitationUsageProjection(
            recorded=len(source_ids),
            source_ids=source_ids,
            citation_keys=citation_keys,
            provenance_link_ids=provenance_link_ids,
        )
