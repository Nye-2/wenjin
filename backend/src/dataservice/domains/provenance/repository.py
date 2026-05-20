"""Provenance graph repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.provenance.models import ProvenanceLinkRecord


class ProvenanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_link(self, values: dict[str, Any]) -> ProvenanceLinkRecord:
        record = ProvenanceLinkRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def list_links(
        self,
        *,
        workspace_id: str,
        source_id: str | None = None,
        target_domain: str | None = None,
        target_id: str | None = None,
        limit: int = 50,
    ) -> list[ProvenanceLinkRecord]:
        query = select(ProvenanceLinkRecord).where(ProvenanceLinkRecord.workspace_id == workspace_id).limit(limit)
        if source_id is not None:
            query = query.where(ProvenanceLinkRecord.source_id == source_id)
        if target_domain is not None:
            query = query.where(ProvenanceLinkRecord.target_domain == target_domain)
        if target_id is not None:
            query = query.where(ProvenanceLinkRecord.target_id == target_id)
        result = await self.session.execute(query.order_by(ProvenanceLinkRecord.created_at.desc()))
        return list(result.scalars().all())
