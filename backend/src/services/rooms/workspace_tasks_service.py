"""Service layer for workspace tasks."""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.workspace_task import WorkspaceTask

logger = logging.getLogger(__name__)


class WorkspaceTasksService:
    """CRUD for workspace_tasks."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[WorkspaceTask] = WorkspaceTask,
    ) -> None:
        self.db = db
        self._model = model

    async def add(
        self, workspace_id: str, data: dict[str, Any]
    ) -> WorkspaceTask:
        """Add a new workspace task."""
        row = self._model(
            id=str(uuid4()),
            workspace_id=workspace_id,
            **data,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def list(
        self, workspace_id: str, status: str | None = None
    ) -> list[WorkspaceTask]:
        """List non-deleted workspace tasks, optionally filtered by status."""
        stmt = (
            select(self._model)
            .where(
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
        )
        if status is not None:
            stmt = stmt.where(self._model.status == status)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get(
        self, workspace_id: str, task_id: str
    ) -> WorkspaceTask | None:
        """Get a single workspace task."""
        result = await self.db.execute(
            select(self._model).where(
                self._model.id == task_id,
                self._model.workspace_id == workspace_id,
                self._model.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self, workspace_id: str, task_id: str, **kwargs: Any
    ) -> WorkspaceTask | None:
        """Update a workspace task.

        If status changes to 'done', automatically sets completed_at.
        """
        task = await self.get(workspace_id, task_id)
        if task is None:
            return None

        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)

        if kwargs.get("status") == "done" and task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def delete(self, workspace_id: str, task_id: str) -> bool:
        """Soft-delete a workspace task. Returns True if found."""
        task = await self.get(workspace_id, task_id)
        if task is None:
            return False
        task.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True
