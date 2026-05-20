"""Workspace library facade backed by DataService Source."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.source_api import SourceCreateCommand, SourceDataService


class LibraryService:
    """Source-backed reference library service."""

    def __init__(self, db: AsyncSession, model: object | None = None) -> None:
        self.db = db
        self._model = model
        self._sources = SourceDataService(db)

    async def add(self, workspace_id: str, data: dict[str, Any]):
        """Add a source-backed library item."""

        return await self._sources.create_source(
            SourceCreateCommand(
                workspace_id=workspace_id,
                source_kind=str(data.get("item_type") or data.get("source_kind") or "paper"),
                title=str(data["title"]),
                authors_json=list(data.get("authors") or data.get("authors_json") or []),
                year=data.get("year"),
                venue=data.get("venue"),
                publication_type=data.get("publication_type"),
                doi=data.get("doi"),
                url=data.get("url"),
                abstract=data.get("abstract"),
                ingest_kind="manual",
                ingest_label=data.get("added_by"),
                library_status=str(data.get("library_status") or "included"),
                citation_key=str(data.get("citation_key") or _citation_key(data)),
                bibtex_fields_json=dict(data.get("bibtex_fields_json") or data.get("metadata_json") or {}),
                tags_json=list(data.get("tags") or []),
                notes=data.get("notes"),
            )
        )

    async def bulk_add(self, workspace_id: str, items: list[dict[str, Any]]):
        """Add multiple source-backed library items."""

        rows = []
        for item_data in items:
            rows.append(await self.add(workspace_id, item_data))
        return rows

    async def list(self, workspace_id: str, limit: int = 100):
        """List active sources for a workspace."""

        return await self._sources.list_sources(
            workspace_id=workspace_id,
            library_status="included",
            include_deleted=False,
            limit=limit,
        )

    async def get(self, workspace_id: str, item_id: str):
        """Get one source-backed library item."""

        source = await self._sources.get_source(item_id)
        if source is None or source.workspace_id != workspace_id or source.is_deleted:
            return None
        return source

    async def delete(self, workspace_id: str, item_id: str) -> bool:
        """Soft-delete a source-backed library item."""

        source = await self.get(workspace_id, item_id)
        if source is None:
            return False
        deleted = await self._sources.mark_deleted(item_id)
        return deleted is not None


def _citation_key(data: dict[str, Any]) -> str:
    raw = str(data.get("doi") or data.get("title") or "source").lower()
    key = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    year = data.get("year")
    if year:
        key = f"{key}_{year}"
    return (key or "source")[:240]
