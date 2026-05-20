"""Source library repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
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
