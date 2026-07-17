"""Repository for hidden workspace memory documents."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.database.models.workspace import Workspace
from src.dataservice.domains.workspace_memory.models import (
    WorkspaceMemoryDocumentRecord,
    WorkspaceMemoryRevisionRecord,
)


class WorkspaceMemoryRepository:
    """Persistence operations for one-memory-document-per-workspace."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_workspace_for_update(self, workspace_id: str) -> None:
        await self.session.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())

    def create_document(self, values: dict[str, Any]) -> WorkspaceMemoryDocumentRecord:
        record = WorkspaceMemoryDocumentRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def create_revision(self, values: dict[str, Any]) -> WorkspaceMemoryRevisionRecord:
        record = WorkspaceMemoryRevisionRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_document(self, workspace_id: str) -> WorkspaceMemoryDocumentRecord | None:
        result = await self.session.execute(select(WorkspaceMemoryDocumentRecord).where(WorkspaceMemoryDocumentRecord.workspace_id == workspace_id).limit(1))
        return result.scalar_one_or_none()

    async def get_revision_by_mission_commit(
        self,
        *,
        workspace_id: str,
        mission_commit_id: str,
    ) -> WorkspaceMemoryRevisionRecord | None:
        result = await self.session.execute(select(WorkspaceMemoryRevisionRecord).where(WorkspaceMemoryRevisionRecord.workspace_id == workspace_id, WorkspaceMemoryRevisionRecord.source_mission_commit_id == mission_commit_id))
        return result.scalar_one_or_none()

    async def list_revisions(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
    ) -> list[WorkspaceMemoryRevisionRecord]:
        result = await self.session.execute(select(WorkspaceMemoryRevisionRecord).where(WorkspaceMemoryRevisionRecord.workspace_id == workspace_id).order_by(WorkspaceMemoryRevisionRecord.revision.desc()).limit(limit))
        return list(result.scalars().all())
