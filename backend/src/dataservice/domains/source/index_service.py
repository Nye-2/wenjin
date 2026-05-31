"""Source full-text index and outline service."""

from __future__ import annotations

from datetime import UTC, datetime

from src.dataservice.domains.source.context import SourceDomainContext
from src.dataservice.domains.source.helpers import serialize_outline_node, serialize_text_unit


class SourceIndexService:
    def __init__(self, context: SourceDomainContext) -> None:
        self.context = context

    async def get_source_outline(
        self,
        workspace_id: str,
        source_id: str,
        *,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        records = await self.context.repository.list_outline_nodes(
            workspace_id=workspace_id,
            source_id=source_id,
            limit=limit,
        )
        return [serialize_outline_node(record) for record in records]

    async def search_text_units(
        self,
        *,
        workspace_id: str,
        query: str,
        source_ids: list[str] | None = None,
        limit: int = 12,
    ) -> list[dict[str, object]]:
        records = await self.context.repository.search_text_units(
            workspace_id=workspace_id,
            query=query,
            source_ids=source_ids,
            limit=limit,
        )
        return [serialize_text_unit(record) for record in records]

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
        node = await self.context.repository.find_outline_node_by_path(
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
        node = await self.context.repository.find_outline_node_by_title(
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
            serialize_text_unit(unit)
            for unit in await self.context.repository.list_text_units_by_outline_node(
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
        records = await self.context.repository.list_text_units_by_pages(
            workspace_id=workspace_id,
            source_id=source_id,
            page_start=page_start,
            page_end=page_end,
        )
        return [serialize_text_unit(record) for record in records]

    async def replace_source_index(
        self,
        *,
        workspace_id: str,
        source_id: str,
        outline_nodes: list[dict[str, object]],
        text_units: list[dict[str, object]],
    ) -> dict[str, int]:
        await self.context.repository.delete_source_index(workspace_id=workspace_id, source_id=source_id)
        for item in outline_nodes:
            self.context.repository.create_outline_node(dict(item))
        for item in text_units:
            self.context.repository.create_text_unit(dict(item))
        source = await self.context.repository.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
            include_deleted=True,
        )
        if source is not None:
            source.fulltext_status = "indexed" if text_units else source.fulltext_status
            source.evidence_level = "indexed_fulltext" if text_units else source.evidence_level
            source.updated_at = datetime.now(UTC)
        await self.context.finish()
        return {"outline_nodes": len(outline_nodes), "text_units": len(text_units)}

    async def _section_from_node(
        self,
        *,
        workspace_id: str,
        source_id: str,
        node: object,
    ) -> dict[str, object]:
        units = [
            serialize_text_unit(unit)
            for unit in await self.context.repository.list_text_units_by_outline_node(
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
