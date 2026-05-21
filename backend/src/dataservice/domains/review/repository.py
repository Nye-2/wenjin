"""Review batch repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.review.models import (
    ReviewActionLogRecord,
    ReviewBatchRecord,
    ReviewItemRecord,
)


class ReviewRepository:
    """Persistence operations for review aggregate rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_batch(self, values: dict[str, Any]) -> ReviewBatchRecord:
        record = ReviewBatchRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def create_item(self, values: dict[str, Any]) -> ReviewItemRecord:
        record = ReviewItemRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def append_action_log(self, values: dict[str, Any]) -> ReviewActionLogRecord:
        record = ReviewActionLogRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_batch(self, batch_id: str) -> ReviewBatchRecord | None:
        result = await self.session.execute(
            select(ReviewBatchRecord).where(ReviewBatchRecord.id == batch_id)
        )
        return result.scalar_one_or_none()

    async def get_item(self, item_id: str) -> ReviewItemRecord | None:
        result = await self.session.execute(
            select(ReviewItemRecord).where(ReviewItemRecord.id == item_id)
        )
        return result.scalar_one_or_none()

    async def list_items(self, batch_id: str) -> list[ReviewItemRecord]:
        result = await self.session.execute(
            select(ReviewItemRecord)
            .where(ReviewItemRecord.batch_id == batch_id)
            .order_by(ReviewItemRecord.sort_order.asc(), ReviewItemRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_items_filtered(
        self,
        *,
        workspace_id: str | None = None,
        execution_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ReviewItemRecord]:
        query = (
            select(ReviewItemRecord)
            .join(ReviewBatchRecord, ReviewBatchRecord.id == ReviewItemRecord.batch_id)
            .order_by(
                func.coalesce(
                    ReviewItemRecord.applied_at,
                    ReviewItemRecord.updated_at,
                    ReviewItemRecord.created_at,
                ).desc()
            )
            .limit(limit)
        )
        if workspace_id is not None:
            query = query.where(ReviewItemRecord.workspace_id == workspace_id)
        if execution_id is not None:
            query = query.where(ReviewBatchRecord.execution_id == execution_id)
        if target_domain is not None:
            query = query.where(ReviewItemRecord.target_domain == target_domain)
        if target_kind is not None:
            query = query.where(ReviewItemRecord.target_kind == target_kind)
        if status is not None:
            query = query.where(ReviewItemRecord.status.in_(status))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_batches(
        self,
        *,
        workspace_id: str | None = None,
        execution_id: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ReviewBatchRecord]:
        query = select(ReviewBatchRecord).order_by(ReviewBatchRecord.created_at.desc()).limit(limit)
        if workspace_id is not None:
            query = query.where(ReviewBatchRecord.workspace_id == workspace_id)
        if execution_id is not None:
            query = query.where(ReviewBatchRecord.execution_id == execution_id)
        if status is not None:
            query = query.where(ReviewBatchRecord.status.in_(status))
        result = await self.session.execute(query)
        return list(result.scalars().all())
