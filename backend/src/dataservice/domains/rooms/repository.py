"""Workspace rooms repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.rooms.models import (
    DecisionRecord,
    MemoryFactRecord,
    WorkspaceTaskRecord,
)


class RoomsRepository:
    """Persistence operations for canonical room tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_decision(self, *, workspace_id: str, key: str) -> DecisionRecord | None:
        result = await self.session.execute(
            select(DecisionRecord).where(
                DecisionRecord.workspace_id == workspace_id,
                DecisionRecord.key == key,
                DecisionRecord.deleted_at.is_(None),
                DecisionRecord.superseded_by.is_(None),
            )
        )
        return result.scalar_one_or_none()

    def create_decision(self, values: dict[str, Any]) -> DecisionRecord:
        record = DecisionRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_decision(self, *, workspace_id: str, decision_id: str) -> DecisionRecord | None:
        result = await self.session.execute(
            select(DecisionRecord).where(
                DecisionRecord.workspace_id == workspace_id,
                DecisionRecord.id == decision_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_decision_by_id(self, decision_id: str) -> DecisionRecord | None:
        result = await self.session.execute(
            select(DecisionRecord).where(DecisionRecord.id == decision_id)
        )
        return result.scalar_one_or_none()

    async def list_active_decisions(self, workspace_id: str) -> list[DecisionRecord]:
        result = await self.session.execute(
            select(DecisionRecord).where(
                DecisionRecord.workspace_id == workspace_id,
                DecisionRecord.deleted_at.is_(None),
                DecisionRecord.superseded_by.is_(None),
            )
        )
        return list(result.scalars().all())

    def create_memory_fact(self, values: dict[str, Any]) -> MemoryFactRecord:
        record = MemoryFactRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def list_memory_facts(
        self,
        *,
        workspace_id: str,
        limit: int = 15,
        category: str | None = None,
    ) -> list[MemoryFactRecord]:
        query = (
            select(MemoryFactRecord)
            .where(
                MemoryFactRecord.workspace_id == workspace_id,
                MemoryFactRecord.deleted_at.is_(None),
            )
            .order_by(MemoryFactRecord.reference_count.desc(), MemoryFactRecord.confidence.desc())
            .limit(limit)
        )
        if category is not None:
            query = query.where(MemoryFactRecord.category == category)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_memory_fact(self, fact_id: str) -> MemoryFactRecord | None:
        result = await self.session.execute(
            select(MemoryFactRecord).where(MemoryFactRecord.id == fact_id)
        )
        return result.scalar_one_or_none()

    async def count_memory_facts(self, workspace_id: str) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(MemoryFactRecord).where(
                MemoryFactRecord.workspace_id == workspace_id,
                MemoryFactRecord.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def list_memory_eviction_candidates(self, *, workspace_id: str, limit: int) -> list[MemoryFactRecord]:
        result = await self.session.execute(
            select(MemoryFactRecord)
            .where(
                MemoryFactRecord.workspace_id == workspace_id,
                MemoryFactRecord.deleted_at.is_(None),
            )
            .order_by(MemoryFactRecord.reference_count.asc(), MemoryFactRecord.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    def create_workspace_task(self, values: dict[str, Any]) -> WorkspaceTaskRecord:
        record = WorkspaceTaskRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_workspace_task(
        self,
        *,
        workspace_id: str,
        task_id: str,
    ) -> WorkspaceTaskRecord | None:
        result = await self.session.execute(
            select(WorkspaceTaskRecord).where(
                WorkspaceTaskRecord.workspace_id == workspace_id,
                WorkspaceTaskRecord.id == task_id,
                WorkspaceTaskRecord.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_workspace_tasks(
        self,
        *,
        workspace_id: str,
        status: str | None = None,
    ) -> list[WorkspaceTaskRecord]:
        query = select(WorkspaceTaskRecord).where(
            WorkspaceTaskRecord.workspace_id == workspace_id,
            WorkspaceTaskRecord.deleted_at.is_(None),
        )
        if status is not None:
            query = query.where(WorkspaceTaskRecord.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())
