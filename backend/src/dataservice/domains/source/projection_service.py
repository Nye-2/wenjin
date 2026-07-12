"""Source projection and listing service."""

from __future__ import annotations

from src.dataservice.domains.source.asset_service import SourceAssetService
from src.dataservice.domains.source.context import SourceDomainContext
from src.dataservice.domains.source.helpers import serialize_reference_projection
from src.dataservice.domains.source.import_service import SourceImportService
from src.dataservice.domains.source.index_service import SourceIndexService
from src.dataservice.domains.source.projection import source_to_projection


class SourceProjectionService:
    def __init__(
        self,
        context: SourceDomainContext,
        *,
        asset_service: SourceAssetService,
        import_service: SourceImportService,
        index_service: SourceIndexService,
    ) -> None:
        self.context = context
        self.asset_service = asset_service
        self.import_service = import_service
        self.index_service = index_service

    async def get_source(self, source_id: str):
        record = await self.context.repository.get_source(source_id)
        return source_to_projection(record) if record else None

    async def get_source_for_workspace(
        self,
        *,
        workspace_id: str,
        source_id: str,
        include_deleted: bool = False,
    ):
        record = await self.context.repository.get_source_for_workspace(
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
        serialized = serialize_reference_projection(source)
        external_ids = await self.import_service.list_source_external_ids(
            workspace_id=workspace_id,
            source_id=source_id,
        )
        assets = await self.asset_service.list_source_assets(workspace_id=workspace_id, source_id=source_id)
        outline = await self.index_service.get_source_outline(workspace_id, source_id, limit=200)
        return {
            "reference": {**serialized, "assets": assets},
            "source": source.model_dump(mode="json"),
            "assets": assets,
            "external_ids": external_ids,
            "source_history": [
                {
                    "source_type": source.ingest_kind,
                    "source_label": source.ingest_label,
                    "source_run_id": source.ingest_mission_id,
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
    ):
        return [
            source_to_projection(record)
            for record in await self.context.repository.list_sources(
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
                    **serialize_reference_projection(item),
                    "assets": await self.asset_service.list_source_assets(
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
        return await self.context.repository.count_sources(
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
        sources = await self.context.repository.list_sources(
            workspace_id=workspace_id,
            include_deleted=False,
            limit=500,
        )
        output: list[dict[str, object]] = []
        for source in sources:
            if str(source.library_status) == "excluded":
                continue
            nodes = await self.index_service.get_source_outline(workspace_id, str(source.id), limit=24)
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
            lines.append(f"### [{index}] {source['title']} ({source.get('year') or 'n.d.'}, key={source['citation_key']})")
            nodes = item.get("outline") or []
            if isinstance(nodes, list) and nodes:
                toc = "; ".join(f"{node['section_path']} {node['title']}" for node in nodes[:12] if isinstance(node, dict))
                lines.append(f"- Outline: {toc}")
            else:
                status = source.get("fulltext_status")
                abstract = str(source.get("abstract") or "").strip()
                if abstract:
                    lines.append(f"- Metadata/abstract only: {' '.join(abstract.split())[:240]}")
                else:
                    lines.append(f"- Full-text status: {status}; no outline is available yet.")
        return "\n".join(lines)
