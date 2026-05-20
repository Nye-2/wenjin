"""Workspace sandbox service facade backed by DataService sandbox aggregate."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.sandbox_api import (
    SandboxDataService,
    SandboxEnvironmentCreateCommand,
    SandboxEnvironmentUpdateCommand,
)


class SandboxService:
    """Compatibility facade whose environment state lives in DataService."""

    def __init__(self, db: AsyncSession, model: object | None = None) -> None:
        self.db = db
        self._model = model
        self._sandbox = SandboxDataService(db)

    async def get_or_create(self, workspace_id: str, provider: str = "local"):
        """Get existing active sandbox or create a new one."""

        return await self._sandbox.get_or_create_environment(
            SandboxEnvironmentCreateCommand(workspace_id=workspace_id, provider=provider)
        )

    async def release(self, workspace_id: str):
        """Set the active sandbox state to stopped."""

        environments = await self._sandbox.list_environments(workspace_id=workspace_id, state="active", limit=1)
        if not environments:
            return None
        return await self._sandbox.update_environment(
            environments[0].id,
            SandboxEnvironmentUpdateCommand(state="stopped"),
        )

    async def update_state(self, workspace_id: str, state: str):
        """Update active sandbox state."""

        environments = await self._sandbox.list_environments(workspace_id=workspace_id, state="active", limit=1)
        if not environments:
            return None
        return await self._sandbox.update_environment(
            environments[0].id,
            SandboxEnvironmentUpdateCommand(state=state),
        )

    async def touch(self, workspace_id: str):
        """Refresh last_active_at by resolving the active sandbox."""

        return await self.get_or_create(workspace_id)
