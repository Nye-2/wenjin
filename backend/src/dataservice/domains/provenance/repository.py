"""Provenance graph repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
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
        target_kind: str | None = None,
        target_id: str | None = None,
        mission_review_item_id: str | None = None,
        relation_kind: str | None = None,
        limit: int = 50,
    ) -> list[ProvenanceLinkRecord]:
        query = select(ProvenanceLinkRecord).where(ProvenanceLinkRecord.workspace_id == workspace_id).limit(limit)
        if source_id is not None:
            query = query.where(ProvenanceLinkRecord.source_id == source_id)
        if target_domain is not None:
            query = query.where(ProvenanceLinkRecord.target_domain == target_domain)
        if target_kind is not None:
            query = query.where(ProvenanceLinkRecord.target_kind == target_kind)
        if target_id is not None:
            query = query.where(ProvenanceLinkRecord.target_id == target_id)
        if mission_review_item_id is not None:
            query = query.where(ProvenanceLinkRecord.mission_review_item_id == mission_review_item_id)
        if relation_kind is not None:
            query = query.where(ProvenanceLinkRecord.relation_kind == relation_kind)
        result = await self.session.execute(query.order_by(ProvenanceLinkRecord.created_at.desc()))
        return list(result.scalars().all())

    async def delete_links(
        self,
        *,
        workspace_id: str,
        source_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        mission_review_item_id: str | None = None,
        relation_kind: str | None = None,
    ) -> int:
        query = delete(ProvenanceLinkRecord).where(ProvenanceLinkRecord.workspace_id == workspace_id)
        if source_id is not None:
            query = query.where(ProvenanceLinkRecord.source_id == source_id)
        if target_domain is not None:
            query = query.where(ProvenanceLinkRecord.target_domain == target_domain)
        if target_kind is not None:
            query = query.where(ProvenanceLinkRecord.target_kind == target_kind)
        if target_id is not None:
            query = query.where(ProvenanceLinkRecord.target_id == target_id)
        if mission_review_item_id is not None:
            query = query.where(ProvenanceLinkRecord.mission_review_item_id == mission_review_item_id)
        if relation_kind is not None:
            query = query.where(ProvenanceLinkRecord.relation_kind == relation_kind)
        result = await self.session.execute(query)
        return int(result.rowcount or 0)
