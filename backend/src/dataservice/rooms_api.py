"""Public in-process rooms API for DataService."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.rooms.contracts import (
    DecisionProjection,
    DecisionSetCommand,
    WorkspaceTaskCreateCommand,
    WorkspaceTaskProjection,
    WorkspaceTaskUpdateCommand,
)
from src.dataservice.domains.rooms.service import RoomsDataDomainService


class RoomsDataService:
    """Rooms API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self._domain = RoomsDataDomainService(session, autocommit=autocommit)

    async def set_decision(self, command: DecisionSetCommand) -> DecisionProjection:
        return await self._domain.set_decision(command)

    async def list_active_decisions(self, workspace_id: str) -> list[DecisionProjection]:
        return await self._domain.list_active_decisions(workspace_id)

    async def delete_decision(self, decision_id: str) -> bool:
        return await self._domain.delete_decision(decision_id)

    async def create_workspace_task(self, command: WorkspaceTaskCreateCommand) -> WorkspaceTaskProjection:
        return await self._domain.create_workspace_task(command)

    async def list_workspace_tasks(
        self,
        *,
        workspace_id: str,
        status: str | None = None,
    ) -> list[WorkspaceTaskProjection]:
        return await self._domain.list_workspace_tasks(workspace_id=workspace_id, status=status)

    async def update_workspace_task(
        self,
        *,
        workspace_id: str,
        task_id: str,
        command: WorkspaceTaskUpdateCommand,
    ) -> WorkspaceTaskProjection | None:
        return await self._domain.update_workspace_task(
            workspace_id=workspace_id,
            task_id=task_id,
            command=command,
        )

    async def soft_delete_workspace_task(self, *, workspace_id: str, task_id: str) -> bool:
        return await self._domain.soft_delete_workspace_task(workspace_id=workspace_id, task_id=task_id)
