"""Workspace settings room facade backed by DataService Workspace."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.workspace_api import WorkspaceDataService, WorkspaceSettingsRecord


class WorkspaceSettingsService:
    """Workspace settings service facade."""

    def __init__(self, db: AsyncSession, model: object | None = None) -> None:
        self.db = db
        self._model = model
        self._workspaces = WorkspaceDataService(db)

    async def get_or_create(self, workspace_id: str) -> WorkspaceSettingsRecord:
        """Fetch existing settings for a workspace, or create DataService defaults."""

        return await self._workspaces.get_or_create_workspace_settings(workspace_id)

    async def update(
        self,
        workspace_id: str,
        **kwargs: Any,
    ) -> WorkspaceSettingsRecord | None:
        """Update one or more settings fields for a workspace."""

        return await self._workspaces.update_workspace_settings(workspace_id, **kwargs)

    async def get(self, workspace_id: str) -> WorkspaceSettingsRecord | None:
        """Fetch settings for a workspace, returning None if absent."""

        return await self._workspaces.get_workspace_settings(workspace_id)

    async def delete(self, workspace_id: str) -> bool:
        """Delete settings for a workspace. Returns True if a row was removed."""

        return await self._workspaces.delete_workspace_settings(workspace_id)
