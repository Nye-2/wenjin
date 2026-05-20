"""Workspace task service facade backed by DataService rooms."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.rooms_api import RoomsDataService, WorkspaceTaskCreateCommand, WorkspaceTaskUpdateCommand


class WorkspaceTasksService:
    """Compatibility facade whose business logic lives in DataService."""

    def __init__(self, db: AsyncSession, model: object | None = None) -> None:
        self.db = db
        self._model = model
        self._rooms = RoomsDataService(db)

    async def add(self, workspace_id: str, data: dict[str, Any]):
        """Add a new workspace task."""

        return await self._rooms.create_workspace_task(
            WorkspaceTaskCreateCommand(workspace_id=workspace_id, **data)
        )

    async def list(self, workspace_id: str, status: str | None = None):
        """List non-deleted workspace tasks, optionally filtered by status."""

        return await self._rooms.list_workspace_tasks(workspace_id=workspace_id, status=status)

    async def get(self, workspace_id: str, task_id: str):
        """Get a single workspace task."""

        tasks = await self._rooms.list_workspace_tasks(workspace_id=workspace_id)
        return next((task for task in tasks if task.id == task_id), None)

    async def update(self, workspace_id: str, task_id: str, **kwargs: Any):
        """Update a workspace task."""

        return await self._rooms.update_workspace_task(
            workspace_id=workspace_id,
            task_id=task_id,
            command=WorkspaceTaskUpdateCommand(**kwargs),
        )

    async def delete(self, workspace_id: str, task_id: str) -> bool:
        """Soft-delete a workspace task. Returns True if found."""

        return await self._rooms.soft_delete_workspace_task(workspace_id=workspace_id, task_id=task_id)
