"""Public in-process API for hidden workspace memory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.workspace_memory.contracts import (
    WorkspaceMemoryDocumentProjection,
    WorkspaceMemoryMergeCommand,
    WorkspaceMemoryRevisionProjection,
    WorkspaceMemoryRewriteCommand,
    WorkspaceMemoryWriteProjection,
)
from src.dataservice.domains.workspace_memory.service import (
    WorkspaceMemoryDataDomainService,
    format_workspace_memory_for_prompt,
)


class WorkspaceMemoryDataService:
    """Workspace memory API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = WorkspaceMemoryDataDomainService(session, autocommit=autocommit)

    async def get_document(self, workspace_id: str) -> WorkspaceMemoryDocumentProjection | None:
        return await self._domain.get_document(workspace_id)

    async def ensure_document(
        self,
        *,
        workspace_id: str,
        created_by: str = "system",
    ) -> WorkspaceMemoryDocumentProjection:
        return await self._domain.ensure_document(workspace_id=workspace_id, created_by=created_by)

    async def rewrite_document(self, command: WorkspaceMemoryRewriteCommand) -> WorkspaceMemoryWriteProjection:
        return await self._domain.rewrite_document(command)

    async def merge_items(self, command: WorkspaceMemoryMergeCommand) -> WorkspaceMemoryWriteProjection:
        return await self._domain.merge_items(command)

    async def list_revisions(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
    ) -> list[WorkspaceMemoryRevisionProjection]:
        return await self._domain.list_revisions(workspace_id=workspace_id, limit=limit)

    async def format_for_prompt(self, workspace_id: str) -> str:
        return format_workspace_memory_for_prompt(await self.get_document(workspace_id))


__all__ = ["WorkspaceMemoryDataService"]
