"""Source library repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.asset.models import WorkspaceAssetRecord
from src.dataservice.domains.source.models import (
    SourceAssetRecord,
    SourceExternalIdRecord,
    SourceOutlineNodeRecord,
    SourceRecord,
    SourceTextUnitRecord,
)


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_source(self, values: dict[str, Any]) -> SourceRecord:
        record = SourceRecord(id=str(values.pop("source_id", None) or generate_uuid()), **values)
        self.session.add(record)
        return record

    def create_outline_node(self, values: dict[str, Any]) -> SourceOutlineNodeRecord:
        record = SourceOutlineNodeRecord(id=str(values.pop("id", None) or generate_uuid()), **values)
        self.session.add(record)
        return record

    def create_text_unit(self, values: dict[str, Any]) -> SourceTextUnitRecord:
        record = SourceTextUnitRecord(id=str(values.pop("id", None) or generate_uuid()), **values)
        self.session.add(record)
        return record

    def create_source_asset(self, values: dict[str, Any]) -> SourceAssetRecord:
        record = SourceAssetRecord(id=str(values.pop("id", None) or generate_uuid()), **values)
        self.session.add(record)
        return record

    def create_external_id(self, values: dict[str, Any]) -> SourceExternalIdRecord:
        record = SourceExternalIdRecord(id=str(values.pop("id", None) or generate_uuid()), **values)
        self.session.add(record)
        return record

    async def get_source_asset(self, source_asset_id: str) -> SourceAssetRecord | None:
        result = await self.session.execute(
            select(SourceAssetRecord).where(SourceAssetRecord.id == source_asset_id)
        )
        return result.scalar_one_or_none()

    async def get_source(self, source_id: str) -> SourceRecord | None:
        result = await self.session.execute(select(SourceRecord).where(SourceRecord.id == source_id))
        return result.scalar_one_or_none()

    async def get_external_id(
        self,
        *,
        workspace_id: str,
        provider: str,
        external_id: str,
    ) -> SourceExternalIdRecord | None:
        result = await self.session.execute(
            select(SourceExternalIdRecord).where(
                SourceExternalIdRecord.workspace_id == workspace_id,
                SourceExternalIdRecord.provider == provider,
                SourceExternalIdRecord.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_external_ids(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> list[SourceExternalIdRecord]:
        result = await self.session.execute(
            select(SourceExternalIdRecord)
            .where(
                SourceExternalIdRecord.workspace_id == workspace_id,
                SourceExternalIdRecord.source_id == source_id,
            )
            .order_by(SourceExternalIdRecord.provider.asc(), SourceExternalIdRecord.external_id.asc())
        )
        return list(result.scalars().all())

    async def get_source_for_workspace(
        self,
        *,
        workspace_id: str,
        source_id: str,
        include_deleted: bool = False,
    ) -> SourceRecord | None:
        query = select(SourceRecord).where(
            SourceRecord.workspace_id == workspace_id,
            SourceRecord.id == source_id,
        )
        if not include_deleted:
            query = query.where(SourceRecord.is_deleted.is_(False))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_sources_by_ids(
        self,
        *,
        workspace_id: str,
        source_ids: list[str],
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> list[SourceRecord]:
        if not source_ids:
            return []
        query = select(SourceRecord).where(
            SourceRecord.workspace_id == workspace_id,
            SourceRecord.id.in_(source_ids),
        )
        if not include_deleted:
            query = query.where(SourceRecord.is_deleted.is_(False))
        if not include_excluded:
            query = query.where(SourceRecord.library_status != "excluded")
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def find_source_by_doi(
        self,
        *,
        workspace_id: str,
        doi: str,
        include_deleted: bool = False,
    ) -> SourceRecord | None:
        query = select(SourceRecord).where(
            SourceRecord.workspace_id == workspace_id,
            SourceRecord.doi == doi,
        )
        if not include_deleted:
            query = query.where(SourceRecord.is_deleted.is_(False))
        result = await self.session.execute(query.limit(1))
        return result.scalar_one_or_none()

    async def find_source_by_title_year(
        self,
        *,
        workspace_id: str,
        normalized_title: str,
        year: int | None,
        include_deleted: bool = False,
    ) -> SourceRecord | None:
        query = select(SourceRecord).where(
            SourceRecord.workspace_id == workspace_id,
            SourceRecord.normalized_title == normalized_title,
        )
        if year is not None:
            query = query.where(SourceRecord.year == year)
        if not include_deleted:
            query = query.where(SourceRecord.is_deleted.is_(False))
        result = await self.session.execute(query.limit(1))
        return result.scalar_one_or_none()

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
    ) -> list[SourceRecord]:
        stmt = select(SourceRecord).where(SourceRecord.workspace_id == workspace_id)
        if library_status is not None:
            stmt = stmt.where(SourceRecord.library_status == library_status)
        elif not include_excluded:
            stmt = stmt.where(SourceRecord.library_status != "excluded")
        if source_kind is not None:
            stmt = stmt.where(SourceRecord.source_kind == source_kind)
        if ingest_kind is not None:
            stmt = stmt.where(SourceRecord.ingest_kind == ingest_kind)
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    SourceRecord.title.ilike(pattern),
                    SourceRecord.venue.ilike(pattern),
                    SourceRecord.doi.ilike(pattern),
                    SourceRecord.abstract.ilike(pattern),
                    SourceRecord.citation_key.ilike(pattern),
                )
            )
        if not include_deleted:
            stmt = stmt.where(SourceRecord.is_deleted.is_(False))
        result = await self.session.execute(
            stmt.order_by(SourceRecord.updated_at.desc())
            .offset(max(0, int(offset)))
            .limit(max(1, min(int(limit), 5000)))
        )
        return list(result.scalars().all())

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
        stmt = select(func.count()).select_from(SourceRecord).where(SourceRecord.workspace_id == workspace_id)
        if library_status is not None:
            stmt = stmt.where(SourceRecord.library_status == library_status)
        elif not include_excluded:
            stmt = stmt.where(SourceRecord.library_status != "excluded")
        if source_kind is not None:
            stmt = stmt.where(SourceRecord.source_kind == source_kind)
        if ingest_kind is not None:
            stmt = stmt.where(SourceRecord.ingest_kind == ingest_kind)
        if fulltext_status is not None:
            stmt = stmt.where(SourceRecord.fulltext_status == fulltext_status)
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    SourceRecord.title.ilike(pattern),
                    SourceRecord.venue.ilike(pattern),
                    SourceRecord.doi.ilike(pattern),
                    SourceRecord.abstract.ilike(pattern),
                    SourceRecord.citation_key.ilike(pattern),
                )
            )
        if not include_deleted:
            stmt = stmt.where(SourceRecord.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def citation_key_exists(
        self,
        *,
        workspace_id: str,
        citation_key: str,
        exclude_source_id: str | None = None,
    ) -> bool:
        stmt = select(SourceRecord.id).where(
            SourceRecord.workspace_id == workspace_id,
            SourceRecord.citation_key == citation_key,
            SourceRecord.is_deleted.is_(False),
        )
        if exclude_source_id:
            stmt = stmt.where(SourceRecord.id != exclude_source_id)
        result = await self.session.execute(stmt.limit(1))
        return result.scalar_one_or_none() is not None

    async def delete_source_index(self, *, workspace_id: str, source_id: str) -> None:
        await self.session.execute(
            delete(SourceTextUnitRecord).where(
                SourceTextUnitRecord.workspace_id == workspace_id,
                SourceTextUnitRecord.source_id == source_id,
            )
        )
        await self.session.execute(
            delete(SourceOutlineNodeRecord).where(
                SourceOutlineNodeRecord.workspace_id == workspace_id,
                SourceOutlineNodeRecord.source_id == source_id,
            )
        )

    async def list_source_assets(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> list[tuple[SourceAssetRecord, WorkspaceAssetRecord | None]]:
        result = await self.session.execute(
            select(SourceAssetRecord, WorkspaceAssetRecord)
            .outerjoin(
                WorkspaceAssetRecord,
                WorkspaceAssetRecord.id == SourceAssetRecord.workspace_asset_id,
            )
            .where(
                SourceAssetRecord.workspace_id == workspace_id,
                SourceAssetRecord.source_id == source_id,
            )
            .order_by(SourceAssetRecord.created_at.desc())
        )
        return [(source_asset, workspace_asset) for source_asset, workspace_asset in result.all()]

    async def list_outline_nodes(
        self,
        *,
        workspace_id: str,
        source_id: str,
        limit: int = 200,
    ) -> list[SourceOutlineNodeRecord]:
        result = await self.session.execute(
            select(SourceOutlineNodeRecord)
            .where(
                SourceOutlineNodeRecord.workspace_id == workspace_id,
                SourceOutlineNodeRecord.source_id == source_id,
            )
            .order_by(SourceOutlineNodeRecord.sort_order.asc())
            .limit(max(1, min(limit, 500)))
        )
        return list(result.scalars().all())

    async def find_outline_node_by_path(
        self,
        *,
        workspace_id: str,
        source_id: str,
        section_path: str,
    ) -> SourceOutlineNodeRecord | None:
        result = await self.session.execute(
            select(SourceOutlineNodeRecord)
            .where(
                SourceOutlineNodeRecord.workspace_id == workspace_id,
                SourceOutlineNodeRecord.source_id == source_id,
                SourceOutlineNodeRecord.section_path == section_path,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_outline_node_by_title(
        self,
        *,
        workspace_id: str,
        source_id: str,
        section_title: str,
    ) -> SourceOutlineNodeRecord | None:
        result = await self.session.execute(
            select(SourceOutlineNodeRecord)
            .where(
                SourceOutlineNodeRecord.workspace_id == workspace_id,
                SourceOutlineNodeRecord.source_id == source_id,
                SourceOutlineNodeRecord.title.ilike(f"%{section_title}%"),
            )
            .order_by(SourceOutlineNodeRecord.sort_order.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_text_units_by_outline_node(
        self,
        *,
        workspace_id: str,
        source_id: str,
        outline_node_id: str,
    ) -> list[SourceTextUnitRecord]:
        result = await self.session.execute(
            select(SourceTextUnitRecord)
            .where(
                SourceTextUnitRecord.workspace_id == workspace_id,
                SourceTextUnitRecord.source_id == source_id,
                SourceTextUnitRecord.outline_node_id == outline_node_id,
            )
            .order_by(SourceTextUnitRecord.unit_index.asc())
        )
        return list(result.scalars().all())

    async def list_text_units_by_pages(
        self,
        *,
        workspace_id: str,
        source_id: str,
        page_start: int,
        page_end: int,
    ) -> list[SourceTextUnitRecord]:
        result = await self.session.execute(
            select(SourceTextUnitRecord)
            .where(
                SourceTextUnitRecord.workspace_id == workspace_id,
                SourceTextUnitRecord.source_id == source_id,
                SourceTextUnitRecord.page_start.is_not(None),
                SourceTextUnitRecord.page_start <= page_end,
                func.coalesce(
                    SourceTextUnitRecord.page_end,
                    SourceTextUnitRecord.page_start,
                )
                >= page_start,
            )
            .order_by(SourceTextUnitRecord.unit_index.asc())
        )
        return list(result.scalars().all())

    async def search_text_units(
        self,
        *,
        workspace_id: str,
        query: str,
        source_ids: list[str] | None = None,
        limit: int = 12,
    ) -> list[SourceTextUnitRecord]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []
        stmt = select(SourceTextUnitRecord).where(
            SourceTextUnitRecord.workspace_id == workspace_id,
            SourceTextUnitRecord.search_text.ilike(f"%{normalized_query}%"),
        )
        if source_ids:
            stmt = stmt.where(SourceTextUnitRecord.source_id.in_(source_ids))
        result = await self.session.execute(
            stmt.order_by(SourceTextUnitRecord.updated_at.desc()).limit(max(1, min(limit, 50)))
        )
        return list(result.scalars().all())

    async def list_sources_by_citation_keys(
        self,
        *,
        workspace_id: str,
        citation_keys: list[str],
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> list[SourceRecord]:
        if not citation_keys:
            return []
        query = select(SourceRecord).where(
            SourceRecord.workspace_id == workspace_id,
            SourceRecord.citation_key.in_(citation_keys),
        )
        if not include_deleted:
            query = query.where(SourceRecord.is_deleted.is_(False))
        if not include_excluded:
            query = query.where(SourceRecord.library_status != "excluded")
        result = await self.session.execute(query.order_by(SourceRecord.citation_key.asc()))
        return list(result.scalars().all())
