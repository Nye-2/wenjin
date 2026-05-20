"""Workspace aggregate command service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.workspace import Workspace
from src.dataservice.common.errors import DataServiceConflictError, DataServiceNotFoundError
from src.dataservice.domains.workspace.contracts import WorkspaceCreateCommand, WorkspaceRecord, WorkspaceUpdateCommand
from src.dataservice.domains.workspace.policies import normalize_workspace_type, with_rollout_defaults
from src.dataservice.domains.workspace.repository import WorkspaceRepository


class DataServiceWorkspaceService:
    """DataService-owned workspace aggregate operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = WorkspaceRepository(session)

    async def create_workspace(self, command: WorkspaceCreateCommand) -> Workspace:
        settings_json = with_rollout_defaults(command.workspace_type, command.settings_json)
        workspace = self.repository.create_workspace(
            created_by_user_id=command.created_by_user_id,
            name=command.name,
            workspace_type=command.workspace_type,
            discipline=command.discipline,
            description=command.description,
            settings_json=settings_json,
        )
        await self.session.flush()
        self.repository.create_owner_membership(
            workspace_id=str(workspace.id),
            user_id=command.created_by_user_id,
        )
        self.repository.create_workspace_settings(
            workspace_id=str(workspace.id),
            settings_json=settings_json,
        )
        if self.autocommit:
            await self.session.commit()
            await self.session.refresh(workspace)
        else:
            await self.session.flush()
        return workspace

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        return await self.repository.get_workspace(workspace_id)

    async def list_workspaces_for_member(self, user_id: str) -> list[Workspace]:
        return await self.repository.list_workspaces_for_member(user_id)

    async def user_has_active_membership(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> bool:
        return await self.repository.has_active_membership(workspace_id=workspace_id, user_id=user_id)

    async def update_workspace(self, workspace_id: str, command: WorkspaceUpdateCommand) -> Workspace | None:
        workspace = await self.repository.get_workspace(workspace_id)
        if workspace is None:
            return None
        return await self.update_loaded_workspace(workspace, command)

    async def update_loaded_workspace(self, workspace: Workspace, command: WorkspaceUpdateCommand) -> Workspace:
        """Apply a workspace update command to an already-loaded workspace."""
        if command.name is not None:
            workspace.name = command.name
        if command.workspace_type is not None:
            workspace.type = normalize_workspace_type(command.workspace_type)
        if "discipline" in command.model_fields_set:
            workspace.discipline = command.discipline
        if "description" in command.model_fields_set:
            workspace.description = command.description

        if command.settings_json is not None:
            next_settings = with_rollout_defaults(command.workspace_type or workspace.type, command.settings_json)
            workspace.config = next_settings
            settings = getattr(workspace, "settings", None)
            if settings is not None and hasattr(settings, "settings_json"):
                settings.settings_json = next_settings
            else:
                await self.repository.ensure_workspace_settings(
                    workspace_id=str(workspace.id),
                    settings_json=next_settings,
                )

        if "active_thread_id" in command.model_fields_set:
            await self.set_active_thread(workspace, command.active_thread_id)

        if self.autocommit:
            await self.session.commit()
            await self.session.refresh(workspace)
        else:
            await self.session.flush()
        return workspace

    async def set_active_thread(self, workspace: Workspace, active_thread_id: str | None) -> None:
        if active_thread_id is None:
            workspace.thread_id = None
            return
        thread = await self.repository.get_thread(active_thread_id)
        if thread is None:
            raise DataServiceNotFoundError("Active thread not found")
        if str(thread.workspace_id or "") != str(workspace.id):
            raise DataServiceConflictError("Active thread must belong to the same workspace")
        workspace.thread_id = active_thread_id

    async def delete_workspace(self, workspace_id: str) -> bool:
        deleted_count = await self.repository.delete_workspace(workspace_id)
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()
        return deleted_count > 0

    @staticmethod
    def to_record(workspace: Workspace) -> WorkspaceRecord:
        settings_json: dict[str, Any] = dict(workspace.config or {})
        settings = getattr(workspace, "settings", None)
        if settings is not None and isinstance(getattr(settings, "settings_json", None), dict):
            settings_json = dict(settings.settings_json)
        return WorkspaceRecord(
            id=str(workspace.id),
            created_by_user_id=str(workspace.user_id),
            name=workspace.name,
            workspace_type=workspace.type,
            discipline=workspace.discipline,
            description=workspace.description,
            settings_json=settings_json,
            active_thread_id=workspace.thread_id,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )
