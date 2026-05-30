"""Source library domain service."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.domains.provenance.projection import provenance_link_to_projection
from src.dataservice.domains.provenance.repository import ProvenanceRepository
from src.dataservice.domains.source.contracts import (
    SourceAssetUpdateCommand,
    SourceBibliographyCreateCommand,
    SourceBibliographyProjection,
    SourceBibliographySnapshotCreateCommand,
    SourceBibliographySnapshotProjection,
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
from src.dataservice.domains.source.projection import (
    source_bibtex_snapshot_to_projection,
    source_to_projection,
)
from src.dataservice.domains.source.repository import SourceRepository

_SOURCE_USED_IN_DRAFT_STATUSES = {"candidate", "included"}
_PROCEEDINGS_BIBTEX_TYPES = {"conference", "inproceedings", "proceedings"}


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

    async def upsert_source(self, command: SourceCreateCommand) -> SourceProjection:
        record = None
        if command.source_id:
            record = await self.repository.get_source_for_workspace(
                workspace_id=command.workspace_id,
                source_id=command.source_id,
                include_deleted=True,
            )
        normalized_title = command.normalized_title or command.title.strip().lower()
        values = {
            **command.model_dump(exclude={"source_id", "normalized_title"}),
            "normalized_title": normalized_title,
        }
        if record is None:
            record = self.repository.create_source(
                {
                    **values,
                    **({"source_id": command.source_id} if command.source_id else {}),
                }
            )
        else:
            for field, value in values.items():
                if hasattr(record, field):
                    setattr(record, field, value)
            record.updated_at = datetime.now(UTC)
        await self._finish()
        return source_to_projection(record)

    async def import_source(self, command: SourceImportCommand) -> SourceImportProjection:
        normalized_title = command.normalized_title or command.title.strip().lower()
        record = await self._find_import_source(command, normalized_title=normalized_title)
        created = record is None
        values = {
            **command.model_dump(
                exclude={
                    "source_id",
                    "normalized_title",
                    "external_ids",
                    "dedupe_by_title",
                }
            ),
            "normalized_title": normalized_title,
            "doi": self._normalize_doi(command.doi),
        }
        if record is None:
            values["citation_key"] = await self._ensure_unique_citation_key(
                workspace_id=command.workspace_id,
                base_key=command.citation_key,
            )
            record = self.repository.create_source(
                {
                    **values,
                    **({"source_id": command.source_id} if command.source_id else {}),
                }
            )
        else:
            self._merge_import_values(record, values)
        await self._finish()
        external_ids = await self.upsert_source_external_ids(
            workspace_id=command.workspace_id,
            source_id=str(record.id),
            external_ids=command.external_ids,
        )
        return SourceImportProjection(
            source=source_to_projection(record),
            created=created,
            external_ids=external_ids,
        )

    async def get_source(self, source_id: str) -> SourceProjection | None:
        record = await self.repository.get_source(source_id)
        return source_to_projection(record) if record else None

    async def get_source_for_workspace(
        self,
        *,
        workspace_id: str,
        source_id: str,
        include_deleted: bool = False,
    ) -> SourceProjection | None:
        record = await self.repository.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
            include_deleted=include_deleted,
        )
        return source_to_projection(record) if record else None

    async def get_source_detail(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> dict[str, object] | None:
        source = await self.get_source_for_workspace(workspace_id=workspace_id, source_id=source_id)
        if source is None:
            return None
        serialized = self._serialize_reference_projection(source)
        external_ids = await self.list_source_external_ids(workspace_id=workspace_id, source_id=source_id)
        assets = await self.list_source_assets(workspace_id=workspace_id, source_id=source_id)
        outline = await self.get_source_outline(workspace_id, source_id, limit=200)
        return {
            "reference": {**serialized, "assets": assets},
            "source": source.model_dump(mode="json"),
            "assets": assets,
            "external_ids": external_ids,
            "source_history": [
                {
                    "source_type": source.ingest_kind,
                    "source_label": source.ingest_label,
                    "source_run_id": source.ingest_execution_id,
                    "verified_at": source.verified_at.isoformat() if source.verified_at else None,
                }
            ],
            "preprocess": {
                "status": source.fulltext_status,
                "markdown_count": 0,
                "has_manifest": False,
            },
            "outline": outline,
            "usage_events": [],
            "usage_summary": {
                "recent_count": 0,
                "status_counts": {},
                "last_used_at": None,
            },
        }

    async def upsert_source_external_ids(
        self,
        *,
        workspace_id: str,
        source_id: str,
        external_ids: list[SourceExternalIdCreateCommand],
    ) -> list[dict[str, object]]:
        source = await self.repository.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
            include_deleted=True,
        )
        if source is None:
            return []
        upserted: list[dict[str, object]] = []
        for item in external_ids:
            provider = item.provider.strip()
            external_id = item.external_id.strip()
            if not provider or not external_id:
                continue
            record = await self.repository.get_external_id(
                workspace_id=workspace_id,
                provider=provider,
                external_id=external_id,
            )
            if record is None:
                record = self.repository.create_external_id(
                    {
                        "workspace_id": workspace_id,
                        "source_id": source_id,
                        "provider": provider,
                        "external_id": external_id,
                        "url": item.url,
                        "metadata_json": dict(item.metadata_json or {}),
                    }
                )
            else:
                record.source_id = source_id
                record.url = record.url or item.url
                record.metadata_json = {
                    **dict(record.metadata_json or {}),
                    **dict(item.metadata_json or {}),
                }
            upserted.append(self._serialize_external_id(record))
        await self._finish()
        return upserted

    async def list_source_external_ids(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> list[dict[str, object]]:
        return [
            self._serialize_external_id(record)
            for record in await self.repository.list_external_ids(
                workspace_id=workspace_id,
                source_id=source_id,
            )
        ]

    async def build_bibliography(
        self,
        command: SourceBibliographyCreateCommand,
    ) -> SourceBibliographyProjection:
        unique_ids = self._normalize_ids(command.source_ids)
        if not command.workspace_id or not unique_ids:
            return SourceBibliographyProjection()

        records = await self.repository.list_sources_by_ids(
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
            content="\n\n".join(self._format_bibtex_entry(record) for record in ordered_records),
            count=len(ordered_records),
            source_ids=[str(record.id) for record in ordered_records],
            citation_keys=[str(record.citation_key) for record in ordered_records],
        )

    async def create_bibliography_snapshot(
        self,
        command: SourceBibliographySnapshotCreateCommand,
    ) -> SourceBibliographySnapshotProjection:
        record = self.repository.create_bibtex_snapshot(command.model_dump())
        await self._finish()
        return source_bibtex_snapshot_to_projection(record)

    async def mark_deleted(self, source_id: str) -> SourceProjection | None:
        record = await self.repository.get_source(source_id)
        if record is None:
            return None
        record.is_deleted = True
        record.updated_at = datetime.now(UTC)
        await self._finish()
        return source_to_projection(record)

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
        values = {
            "workspace_id": workspace_id,
            "source_id": source_id,
            "workspace_asset_id": workspace_asset_id,
            "asset_type": asset_type,
            "preprocess_status": preprocess_status,
            "manifest_asset_id": manifest_asset_id,
            "metadata_json": dict(metadata_json or {}),
        }
        record = await self.repository.get_source_asset(source_asset_id) if source_asset_id else None
        if record is None:
            record = self.repository.create_source_asset(
                {
                    **values,
                    **({"id": source_asset_id} if source_asset_id else {}),
                }
            )
        else:
            for field, value in values.items():
                setattr(record, field, value)
            record.updated_at = datetime.now(UTC)
        await self._finish()
        return self._serialize_source_asset(record, None)

    async def get_source_asset(
        self,
        *,
        workspace_id: str,
        source_asset_id: str,
    ) -> dict[str, object] | None:
        record = await self.repository.get_source_asset(source_asset_id)
        if record is None or str(record.workspace_id) != workspace_id:
            return None
        return self._serialize_source_asset(record, None)

    async def update_source_asset(
        self,
        *,
        workspace_id: str,
        source_asset_id: str,
        command: SourceAssetUpdateCommand,
    ) -> dict[str, object] | None:
        record = await self.repository.get_source_asset(source_asset_id)
        if record is None or str(record.workspace_id) != workspace_id:
            return None
        if command.preprocess_status is not None:
            record.preprocess_status = command.preprocess_status
        if command.manifest_asset_id is not None:
            record.manifest_asset_id = command.manifest_asset_id
        if command.metadata_json is not None:
            record.metadata_json = {
                **dict(record.metadata_json or {}),
                **dict(command.metadata_json or {}),
            }
        record.updated_at = datetime.now(UTC)
        await self._finish()
        return self._serialize_source_asset(record, None)

    async def mark_deleted_for_workspace(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> bool:
        record = await self.repository.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
        )
        if record is None:
            return False
        record.is_deleted = True
        record.updated_at = datetime.now(UTC)
        await self._finish()
        return True

    async def update_source(
        self,
        *,
        workspace_id: str,
        source_id: str,
        command: SourceUpdateCommand,
    ) -> SourceProjection | None:
        record = await self.repository.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
        )
        if record is None:
            return None
        updates = command.model_dump(exclude_unset=True)
        if "title" in updates and updates["title"]:
            updates["normalized_title"] = str(updates["title"]).strip().lower()
        if "doi" in updates and updates["doi"] is not None:
            updates["doi"] = self._normalize_doi(updates["doi"])
        if "citation_key" in updates and updates["citation_key"]:
            updates["citation_key"] = await self._ensure_unique_citation_key(
                workspace_id=workspace_id,
                base_key=str(updates["citation_key"]),
                exclude_source_id=source_id,
            )
        now = datetime.now(UTC)
        for field, value in updates.items():
            if hasattr(record, field):
                setattr(record, field, value)
        record.updated_at = now
        await self._finish()
        return source_to_projection(record)

    async def mark_status(
        self,
        *,
        workspace_id: str,
        source_id: str,
        library_status: str | None = None,
        read_status: str | None = None,
    ) -> SourceProjection | None:
        return await self.update_source(
            workspace_id=workspace_id,
            source_id=source_id,
            command=SourceUpdateCommand(
                **{
                    **({"library_status": library_status} if library_status is not None else {}),
                    **({"read_status": read_status} if read_status is not None else {}),
                }
            ),
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
        return [
            source_to_projection(record)
            for record in await self.repository.list_sources(
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
        ]

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
        items = await self.list_sources(
            workspace_id=workspace_id,
            library_status=library_status,
            source_kind=source_kind,
            ingest_kind=ingest_kind,
            query=query,
            include_deleted=False,
            include_excluded=True,
            offset=offset,
            limit=limit,
        )
        total = await self.count_sources(
            workspace_id=workspace_id,
            library_status=library_status,
            source_kind=source_kind,
            ingest_kind=ingest_kind,
            query=query,
            include_deleted=False,
            include_excluded=True,
        )
        core = await self.count_sources(
            workspace_id=workspace_id,
            library_status="core",
            include_deleted=False,
        )
        return {
            "items": [
                {
                    **self._serialize_reference_projection(item),
                    "assets": await self.list_source_assets(
                        workspace_id=workspace_id,
                        source_id=item.id,
                    ),
                }
                for item in items
            ],
            "total": total,
            "core_count": core,
        }

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
        if not workspace_id:
            return 0
        return await self.repository.count_sources(
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
        total = await self.count_sources(
            workspace_id=workspace_id,
            include_deleted=False,
            include_excluded=False,
        )
        core = await self.count_sources(
            workspace_id=workspace_id,
            library_status="core",
            include_deleted=False,
        )
        indexed = await self.count_sources(
            workspace_id=workspace_id,
            fulltext_status="indexed",
            include_deleted=False,
            include_excluded=True,
        )
        return {"total": total, "core": core, "indexed": indexed}

    async def get_library_outline(self, workspace_id: str) -> list[dict[str, object]]:
        sources = await self.repository.list_sources(
            workspace_id=workspace_id,
            include_deleted=False,
            limit=500,
        )
        output: list[dict[str, object]] = []
        for source in sources:
            if str(source.library_status) == "excluded":
                continue
            nodes = await self.get_source_outline(workspace_id, str(source.id), limit=24)
            output.append(
                {
                    "source": source_to_projection(source).model_dump(mode="json"),
                    "reference": source_to_projection(source).model_dump(mode="json"),
                    "outline": nodes,
                }
            )
        return output

    async def get_workspace_toc_summary(self, workspace_id: str) -> str:
        outline = await self.get_library_outline(workspace_id)
        if not outline:
            return ""
        lines = ["## Source Library Outline"]
        for index, item in enumerate(outline[:30], start=1):
            source = item["source"]
            assert isinstance(source, dict)
            lines.append(
                f"### [{index}] {source['title']} "
                f"({source.get('year') or 'n.d.'}, key={source['citation_key']})"
            )
            nodes = item.get("outline") or []
            if isinstance(nodes, list) and nodes:
                toc = "; ".join(
                    f"{node['section_path']} {node['title']}"
                    for node in nodes[:12]
                    if isinstance(node, dict)
                )
                lines.append(f"- Outline: {toc}")
            else:
                status = source.get("fulltext_status")
                abstract = str(source.get("abstract") or "").strip()
                if abstract:
                    lines.append(f"- Metadata/abstract only: {' '.join(abstract.split())[:240]}")
                else:
                    lines.append(f"- Full-text status: {status}; no outline is available yet.")
        return "\n".join(lines)

    async def list_source_assets(self, *, workspace_id: str, source_id: str) -> list[dict[str, object]]:
        return [
            self._serialize_source_asset(source_asset, workspace_asset)
            for source_asset, workspace_asset in await self.repository.list_source_assets(
                workspace_id=workspace_id,
                source_id=source_id,
            )
        ]

    async def get_source_outline(
        self,
        workspace_id: str,
        source_id: str,
        *,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        records = await self.repository.list_outline_nodes(
            workspace_id=workspace_id,
            source_id=source_id,
            limit=limit,
        )
        return [self._serialize_outline_node(record) for record in records]

    async def search_text_units(
        self,
        *,
        workspace_id: str,
        query: str,
        source_ids: list[str] | None = None,
        limit: int = 12,
    ) -> list[dict[str, object]]:
        records = await self.repository.search_text_units(
            workspace_id=workspace_id,
            query=query,
            source_ids=source_ids,
            limit=limit,
        )
        return [self._serialize_text_unit(record) for record in records]

    async def build_evidence_pack(
        self,
        command: SourceEvidencePackCreateCommand,
    ) -> SourceEvidencePackProjection:
        outline = await self.get_library_outline(command.workspace_id)
        query = command.query.strip() if command.query else None
        selected_units = (
            await self.search_text_units(
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

    async def search_workspace_sections(
        self,
        workspace_id: str,
        query: str,
        *,
        limit: int = 8,
    ) -> list[dict[str, object]]:
        return await self.search_text_units(workspace_id=workspace_id, query=query, limit=limit)

    async def get_source_section(
        self,
        *,
        workspace_id: str,
        source_id: str,
        section_path: str,
    ) -> dict[str, object] | None:
        node = await self.repository.find_outline_node_by_path(
            workspace_id=workspace_id,
            source_id=source_id,
            section_path=section_path,
        )
        if node is None:
            return None
        return await self._section_from_node(workspace_id=workspace_id, source_id=source_id, node=node)

    async def get_source_section_by_title(
        self,
        *,
        workspace_id: str,
        source_id: str,
        section_title: str,
    ) -> dict[str, object] | None:
        node = await self.repository.find_outline_node_by_title(
            workspace_id=workspace_id,
            source_id=source_id,
            section_title=section_title,
        )
        if node is None:
            return None
        return await self._section_from_node(workspace_id=workspace_id, source_id=source_id, node=node)

    async def read_source_outline_node(
        self,
        *,
        workspace_id: str,
        source_id: str,
        outline_node_id: str,
    ) -> dict[str, object] | None:
        units = [
            self._serialize_text_unit(unit)
            for unit in await self.repository.list_text_units_by_outline_node(
                workspace_id=workspace_id,
                source_id=source_id,
                outline_node_id=outline_node_id,
            )
        ]
        if not units:
            return None
        return {"units": units, "content": "\n\n".join(str(unit["content"]) for unit in units)}

    async def read_source_pages(
        self,
        *,
        workspace_id: str,
        source_id: str,
        page_start: int,
        page_end: int,
    ) -> list[dict[str, object]]:
        records = await self.repository.list_text_units_by_pages(
            workspace_id=workspace_id,
            source_id=source_id,
            page_start=page_start,
            page_end=page_end,
        )
        return [self._serialize_text_unit(record) for record in records]

    async def replace_source_index(
        self,
        *,
        workspace_id: str,
        source_id: str,
        outline_nodes: list[dict[str, object]],
        text_units: list[dict[str, object]],
    ) -> dict[str, int]:
        await self.repository.delete_source_index(workspace_id=workspace_id, source_id=source_id)
        for item in outline_nodes:
            self.repository.create_outline_node(dict(item))
        for item in text_units:
            self.repository.create_text_unit(dict(item))
        source = await self.repository.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
            include_deleted=True,
        )
        if source is not None:
            source.fulltext_status = "indexed" if text_units else source.fulltext_status
            source.evidence_level = "indexed_fulltext" if text_units else source.evidence_level
            source.updated_at = datetime.now(UTC)
        await self._finish()
        return {"outline_nodes": len(outline_nodes), "text_units": len(text_units)}

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

    @staticmethod
    def _normalize_ids(ids: list[str]) -> list[str]:
        return [
            item
            for item in dict.fromkeys(str(raw).strip() for raw in ids)
            if item
        ]

    async def _ensure_unique_citation_key(
        self,
        *,
        workspace_id: str,
        base_key: str,
        exclude_source_id: str | None = None,
    ) -> str:
        base = re.sub(r"[^A-Za-z0-9_:-]+", "", str(base_key or "").strip()) or "ref"
        candidate = base
        suffix = 2
        while await self.repository.citation_key_exists(
            workspace_id=workspace_id,
            citation_key=candidate,
            exclude_source_id=exclude_source_id,
        ):
            candidate = f"{base}{suffix}"
            suffix += 1
        return candidate

    async def _find_import_source(
        self,
        command: SourceImportCommand,
        *,
        normalized_title: str,
    ) -> object | None:
        if command.source_id:
            source = await self.repository.get_source_for_workspace(
                workspace_id=command.workspace_id,
                source_id=command.source_id,
                include_deleted=True,
            )
            if source is not None:
                return source
        for external_id in command.external_ids:
            record = await self.repository.get_external_id(
                workspace_id=command.workspace_id,
                provider=external_id.provider,
                external_id=external_id.external_id,
            )
            if record is not None:
                source = await self.repository.get_source_for_workspace(
                    workspace_id=command.workspace_id,
                    source_id=str(record.source_id),
                    include_deleted=False,
                )
                if source is not None:
                    return source
        doi = self._normalize_doi(command.doi)
        if doi:
            source = await self.repository.find_source_by_doi(
                workspace_id=command.workspace_id,
                doi=doi,
            )
            if source is not None:
                return source
        if command.dedupe_by_title and normalized_title:
            return await self.repository.find_source_by_title_year(
                workspace_id=command.workspace_id,
                normalized_title=normalized_title,
                year=command.year,
            )
        return None

    @staticmethod
    def _merge_import_values(record: object, values: dict[str, object]) -> None:
        for field in (
            "title",
            "normalized_title",
            "authors_json",
            "year",
            "venue",
            "publication_type",
            "doi",
            "url",
            "abstract",
            "citation_count",
            "ingest_label",
            "ingest_execution_id",
            "verified_at",
            "bibtex_entry_type",
            "read_status",
            "notes",
        ):
            value = values.get(field)
            if value not in (None, "", [], {}) and not getattr(record, field, None):
                setattr(record, field, value)
        if values.get("bibtex_fields_json"):
            record.bibtex_fields_json = {
                **dict(getattr(record, "bibtex_fields_json", None) or {}),
                **dict(values["bibtex_fields_json"] or {}),
            }
        if values.get("tags_json"):
            record.tags_json = list(
                dict.fromkeys(
                    list(getattr(record, "tags_json", None) or [])
                    + [str(item) for item in values["tags_json"] or []]
                )
            )
        incoming_status = str(values.get("library_status") or "")
        if incoming_status and incoming_status != "candidate":
            record.library_status = incoming_status
        record.evidence_level = SourceDataDomainService._max_ranked_value(
            getattr(record, "evidence_level", None),
            values.get("evidence_level"),
            {
                "metadata_only": 0,
                "external_verified": 1,
                "uploaded_fulltext": 2,
                "indexed_fulltext": 3,
            },
        )
        record.fulltext_status = SourceDataDomainService._max_ranked_value(
            getattr(record, "fulltext_status", None),
            values.get("fulltext_status"),
            {
                "none": 0,
                "failed": 1,
                "uploaded": 2,
                "preprocessing": 3,
                "indexed": 4,
            },
        )
        record.updated_at = datetime.now(UTC)

    @staticmethod
    def _max_ranked_value(current: object, incoming: object, ranks: dict[str, int]) -> str:
        current_value = str(current or "")
        incoming_value = str(incoming or "")
        return incoming_value if ranks.get(incoming_value, 0) > ranks.get(current_value, 0) else current_value

    @staticmethod
    def _format_bibtex_entry(record: object) -> str:
        fields = dict(getattr(record, "bibtex_fields_json", None) or {})
        fields.setdefault("title", getattr(record, "title", None))
        authors = getattr(record, "authors_json", None) or []
        if authors:
            fields.setdefault("author", " and ".join(str(author) for author in authors if author))
        year = getattr(record, "year", None)
        if year:
            fields.setdefault("year", str(year))
        venue = getattr(record, "venue", None)
        entry_type = str(getattr(record, "bibtex_entry_type", None) or "article").strip() or "article"
        if venue:
            field_name = "booktitle" if entry_type in _PROCEEDINGS_BIBTEX_TYPES else "journal"
            fields.setdefault(field_name, venue)
        doi = getattr(record, "doi", None)
        if doi:
            fields.setdefault("doi", doi)
        url = getattr(record, "url", None)
        if url:
            fields.setdefault("url", url)

        rendered_fields = []
        for key in sorted(fields):
            value = SourceDataDomainService._clean_bibtex_value(fields[key])
            if value:
                rendered_fields.append(f"  {key} = {{{value}}}")
        citation_key = SourceDataDomainService._clean_citation_key(
            getattr(record, "citation_key", None),
            default_key=str(getattr(record, "id", "source")),
        )
        joined = ",\n".join(rendered_fields)
        return f"@{entry_type}{{{citation_key},\n{joined}\n}}"

    @staticmethod
    def _clean_bibtex_value(value: object) -> str:
        return str(value or "").replace("{", "").replace("}", "").strip()

    @staticmethod
    def _clean_citation_key(value: object, *, default_key: str) -> str:
        cleaned = str(value or "").strip().replace("{", "").replace("}", "")
        return cleaned or default_key

    @staticmethod
    def _normalize_doi(value: object) -> str | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        lower = normalized.lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if lower.startswith(prefix):
                return normalized[len(prefix) :].strip().lower() or None
        return normalized.lower()

    @staticmethod
    def _serialize_reference_projection(source: SourceProjection) -> dict[str, object]:
        return {
            "id": source.id,
            "workspace_id": source.workspace_id,
            "title": source.title,
            "normalized_title": source.normalized_title,
            "authors": list(source.authors_json or []),
            "year": source.year,
            "venue": source.venue,
            "publication_type": source.publication_type,
            "doi": source.doi,
            "url": source.url,
            "abstract": source.abstract,
            "citation_count": source.citation_count,
            "source_type": source.ingest_kind,
            "source_label": source.ingest_label,
            "source_run_id": source.ingest_execution_id,
            "source_artifact_id": None,
            "verified_at": source.verified_at.isoformat() if source.verified_at else None,
            "library_status": source.library_status,
            "evidence_level": source.evidence_level,
            "fulltext_status": source.fulltext_status,
            "citation_key": source.citation_key,
            "bibtex_entry_type": source.bibtex_entry_type,
            "bibtex_fields": dict(source.bibtex_fields_json or {}),
            "read_status": source.read_status,
            "tags": list(source.tags_json or []),
            "notes": source.notes,
            "is_deleted": bool(source.is_deleted),
            "created_at": source.created_at.isoformat() if source.created_at else None,
            "updated_at": source.updated_at.isoformat() if source.updated_at else None,
        }

    @staticmethod
    def _serialize_source_asset(source_asset: object, workspace_asset: object | None) -> dict[str, object]:
        metadata = dict(getattr(source_asset, "metadata_json", None) or {})
        created_at = getattr(source_asset, "created_at", None)
        updated_at = getattr(source_asset, "updated_at", None)
        return {
            "id": str(source_asset.id),
            "workspace_id": str(source_asset.workspace_id),
            "reference_id": str(source_asset.source_id),
            "source_id": str(source_asset.source_id),
            "workspace_asset_id": str(source_asset.workspace_asset_id),
            "source_asset_id": metadata.get("source_asset_id"),
            "asset_type": getattr(source_asset, "asset_type", None),
            "file_path": getattr(workspace_asset, "storage_path", None) if workspace_asset else metadata.get("file_path"),
            "virtual_path": metadata.get("virtual_path"),
            "public_url": metadata.get("public_url"),
            "content_type": getattr(workspace_asset, "mime_type", None) if workspace_asset else metadata.get("content_type"),
            "file_size": getattr(workspace_asset, "size_bytes", None) if workspace_asset else metadata.get("file_size"),
            "file_hash": getattr(workspace_asset, "content_hash", None) if workspace_asset else metadata.get("file_hash"),
            "page_count": metadata.get("page_count"),
            "language": metadata.get("language"),
            "preprocess_status": getattr(source_asset, "preprocess_status", None),
            "preprocess_task_id": metadata.get("preprocess_task_id"),
            "preprocess_error": metadata.get("preprocess_error"),
            "manifest_path": metadata.get("manifest_path"),
            "markdown_paths": list(metadata.get("markdown_paths") or []),
            "metadata": metadata,
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
        }

    @staticmethod
    def _serialize_external_id(record: object) -> dict[str, object]:
        created_at = getattr(record, "created_at", None)
        updated_at = getattr(record, "updated_at", None)
        provider = getattr(record, "provider", None)
        return {
            "id": str(record.id),
            "workspace_id": str(record.workspace_id),
            "source_id": str(record.source_id),
            "provider": provider,
            "source": provider,
            "external_id": record.external_id,
            "url": getattr(record, "url", None),
            "metadata": dict(getattr(record, "metadata_json", None) or {}),
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
        }

    async def _section_from_node(
        self,
        *,
        workspace_id: str,
        source_id: str,
        node: object,
    ) -> dict[str, object]:
        units = [
            self._serialize_text_unit(unit)
            for unit in await self.repository.list_text_units_by_outline_node(
                workspace_id=workspace_id,
                source_id=source_id,
                outline_node_id=str(node.id),
            )
        ]
        return {
            "source_id": source_id,
            "reference_id": source_id,
            "node_id": str(node.id),
            "title": str(node.title),
            "section_path": str(node.section_path),
            "content": "\n\n".join(str(unit["content"]) for unit in units),
            "units": units,
        }

    @staticmethod
    def _serialize_outline_node(record: object) -> dict[str, object]:
        return {
            "id": str(record.id),
            "workspace_id": str(record.workspace_id),
            "source_id": str(record.source_id),
            "reference_id": str(record.source_id),
            "parent_id": getattr(record, "parent_id", None),
            "section_path": getattr(record, "section_path", None),
            "title": getattr(record, "title", None),
            "level": getattr(record, "level", None),
            "sort_order": getattr(record, "sort_order", None),
            "page_start": getattr(record, "page_start", None),
            "page_end": getattr(record, "page_end", None),
            "summary": getattr(record, "summary", None),
            "keywords": list(getattr(record, "keywords_json", None) or []),
        }

    @staticmethod
    def _serialize_text_unit(record: object) -> dict[str, object]:
        return {
            "id": str(record.id),
            "workspace_id": str(record.workspace_id),
            "source_id": str(record.source_id),
            "reference_id": str(record.source_id),
            "outline_node_id": getattr(record, "outline_node_id", None),
            "asset_id": getattr(record, "source_asset_id", None),
            "unit_type": getattr(record, "unit_type", None),
            "unit_index": getattr(record, "unit_index", None),
            "page_start": getattr(record, "page_start", None),
            "page_end": getattr(record, "page_end", None),
            "content": getattr(record, "content", None),
            "token_count": getattr(record, "token_count", None),
            "metadata": dict(getattr(record, "metadata_json", None) or {}),
            "created_at": getattr(record, "created_at", None),
            "updated_at": getattr(record, "updated_at", None),
        }
