"""Workspace rooms repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.rooms.models import (
    DecisionRecord,
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

    async def get_decision_by_mission_commit(
        self,
        *,
        workspace_id: str,
        source_mission_commit_id: str,
    ) -> DecisionRecord | None:
        result = await self.session.execute(
            select(DecisionRecord)
            .where(
                DecisionRecord.workspace_id == workspace_id,
                DecisionRecord.source_mission_commit_id == source_mission_commit_id,
                DecisionRecord.deleted_at.is_(None),
            )
            .order_by(DecisionRecord.created_at.asc())
        )
        return result.scalars().first()

    async def get_decision_by_extracted_by(
        self,
        *,
        workspace_id: str,
        key: str,
        extracted_by: str,
    ) -> DecisionRecord | None:
        result = await self.session.execute(
            select(DecisionRecord)
            .where(
                DecisionRecord.workspace_id == workspace_id,
                DecisionRecord.key == key,
                DecisionRecord.extracted_by == extracted_by,
                DecisionRecord.deleted_at.is_(None),
            )
            .order_by(DecisionRecord.created_at.asc())
        )
        return result.scalars().first()

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
        result = await self.session.execute(select(DecisionRecord).where(DecisionRecord.id == decision_id))
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

    def create_workspace_task(self, values: dict[str, Any]) -> WorkspaceTaskRecord:
        record = WorkspaceTaskRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_workspace_task_by_mission_commit(
        self,
        *,
        workspace_id: str,
        source_mission_commit_id: str,
    ) -> WorkspaceTaskRecord | None:
        result = await self.session.execute(
            select(WorkspaceTaskRecord)
            .where(
                WorkspaceTaskRecord.workspace_id == workspace_id,
                WorkspaceTaskRecord.source_mission_commit_id == source_mission_commit_id,
                WorkspaceTaskRecord.deleted_at.is_(None),
            )
            .order_by(WorkspaceTaskRecord.created_at.asc())
        )
        return result.scalars().first()

    async def get_workspace_task_by_created_by(
        self,
        *,
        workspace_id: str,
        title: str,
        created_by: str,
    ) -> WorkspaceTaskRecord | None:
        result = await self.session.execute(
            select(WorkspaceTaskRecord)
            .where(
                WorkspaceTaskRecord.workspace_id == workspace_id,
                WorkspaceTaskRecord.title == title,
                WorkspaceTaskRecord.created_by == created_by,
                WorkspaceTaskRecord.deleted_at.is_(None),
            )
            .order_by(WorkspaceTaskRecord.created_at.asc())
        )
        return result.scalars().first()

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
