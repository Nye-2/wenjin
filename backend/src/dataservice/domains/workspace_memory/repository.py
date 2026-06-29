"""Repository for hidden workspace memory documents."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.dataservice.domains.workspace_memory.models import (
    WorkspaceMemoryDocumentRecord,
    WorkspaceMemoryRevisionRecord,
)


class WorkspaceMemoryRepository:
    """Persistence operations for one-memory-document-per-workspace."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_document(self, values: dict[str, Any]) -> WorkspaceMemoryDocumentRecord:
        record = WorkspaceMemoryDocumentRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    def create_revision(self, values: dict[str, Any]) -> WorkspaceMemoryRevisionRecord:
        record = WorkspaceMemoryRevisionRecord(id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_document(self, workspace_id: str) -> WorkspaceMemoryDocumentRecord | None:
        result = await self.session.execute(
            select(WorkspaceMemoryDocumentRecord)
            .where(WorkspaceMemoryDocumentRecord.workspace_id == workspace_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_revisions(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
    ) -> list[WorkspaceMemoryRevisionRecord]:
        result = await self.session.execute(
            select(WorkspaceMemoryRevisionRecord)
            .where(WorkspaceMemoryRevisionRecord.workspace_id == workspace_id)
            .order_by(WorkspaceMemoryRevisionRecord.revision.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
