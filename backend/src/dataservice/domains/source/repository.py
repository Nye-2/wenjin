"""Source library repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.source.models import SourceRecord


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_source(self, values: dict[str, Any]) -> SourceRecord:
        record = SourceRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_source(self, source_id: str) -> SourceRecord | None:
        result = await self.session.execute(select(SourceRecord).where(SourceRecord.id == source_id))
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

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[SourceRecord]:
        query = select(SourceRecord).where(SourceRecord.workspace_id == workspace_id).limit(limit)
        if library_status is not None:
            query = query.where(SourceRecord.library_status == library_status)
        if not include_deleted:
            query = query.where(SourceRecord.is_deleted.is_(False))
        result = await self.session.execute(query.order_by(SourceRecord.created_at.desc()))
        return list(result.scalars().all())

    async def count_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> int:
        query = select(func.count()).select_from(SourceRecord).where(SourceRecord.workspace_id == workspace_id)
        if library_status is not None:
            query = query.where(SourceRecord.library_status == library_status)
        elif not include_excluded:
            query = query.where(SourceRecord.library_status != "excluded")
        if not include_deleted:
            query = query.where(SourceRecord.is_deleted.is_(False))
        result = await self.session.execute(query)
        return int(result.scalar() or 0)

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
