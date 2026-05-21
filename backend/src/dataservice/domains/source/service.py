"""Source library domain service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.provenance.contracts import ProvenanceLinkCreateCommand
from src.dataservice.domains.provenance.projection import provenance_link_to_projection
from src.dataservice.domains.provenance.repository import ProvenanceRepository
from src.dataservice.domains.source.contracts import (
    SourceBibliographyCreateCommand,
    SourceBibliographyProjection,
    SourceCitationUsageCreateCommand,
    SourceCitationUsageProjection,
    SourceCreateCommand,
    SourceProjection,
)
from src.dataservice.domains.source.projection import source_to_projection
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

    async def get_source(self, source_id: str) -> SourceProjection | None:
        record = await self.repository.get_source(source_id)
        return source_to_projection(record) if record else None

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

    async def count_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> int:
        if not workspace_id:
            return 0
        return await self.repository.count_sources(
            workspace_id=workspace_id,
            library_status=library_status,
            include_deleted=include_deleted,
            include_excluded=include_excluded,
        )

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
            fallback=str(getattr(record, "id", "source")),
        )
        joined = ",\n".join(rendered_fields)
        return f"@{entry_type}{{{citation_key},\n{joined}\n}}"

    @staticmethod
    def _clean_bibtex_value(value: object) -> str:
        return str(value or "").replace("{", "").replace("}", "").strip()

    @staticmethod
    def _clean_citation_key(value: object, *, fallback: str) -> str:
        cleaned = str(value or "").strip().replace("{", "").replace("}", "")
        return cleaned or fallback

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
