"""Public in-process workspace API for DataService.

Runtime code depends on this module while the domain implementation stays inside
``src.dataservice.domains``. The same method surface is mirrored by the HTTP
DataService client as the deployment moves to a fully separate service.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Workspace, WorkspaceType
from src.dataservice.domains.workspace.contracts import (
    WorkspaceAdminStatsRecord,
    WorkspaceCreateCommand,
    WorkspaceSettingsRecord,
    WorkspaceSettingsUpdateCommand,
    WorkspaceStatsRecord,
    WorkspaceUpdateCommand,
)
from src.dataservice.domains.workspace.policies import normalize_workspace_type, with_rollout_defaults
from src.dataservice.domains.workspace.service import DataServiceWorkspaceService


class WorkspaceDataService:
    """Workspace aggregate API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceWorkspaceService(session, autocommit=autocommit)

    @staticmethod
    def normalize_workspace_type(value: WorkspaceType | str) -> WorkspaceType:
        return normalize_workspace_type(value)

    @staticmethod
    def with_rollout_defaults(
        workspace_type: WorkspaceType | str,
        settings_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return with_rollout_defaults(workspace_type, settings_json)

    async def create_workspace(
        self,
        *,
        created_by_user_id: str,
        name: str,
        workspace_type: WorkspaceType | str,
        discipline: str | None = None,
        description: str | None = None,
        settings_json: dict[str, Any] | None = None,
    ) -> Workspace:
        return await self._domain.create_workspace(
            WorkspaceCreateCommand(
                created_by_user_id=created_by_user_id,
                name=name,
                workspace_type=normalize_workspace_type(workspace_type),
                discipline=discipline,
                description=description,
                settings_json=settings_json or {},
            )
        )

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        return await self._domain.get_workspace(workspace_id)

    async def get_workspace_bridge_row(self, workspace_id: str) -> dict[str, Any] | None:
        return await self._domain.get_workspace_bridge_row(workspace_id)

    async def lock_workspace_for_update(self, workspace_id: str) -> None:
        await self._domain.lock_workspace_for_update(workspace_id)

    async def list_workspaces_for_member(self, user_id: str) -> list[Workspace]:
        return await self._domain.list_workspaces_for_member(user_id)

    async def get_workspace_stats_for_member(self, user_id: str) -> WorkspaceStatsRecord:
        return await self._domain.get_workspace_stats_for_member(user_id)

    async def get_admin_workspace_stats(self) -> WorkspaceAdminStatsRecord:
        return await self._domain.get_admin_workspace_stats()

    async def count_workspaces_by_member_ids(self, user_ids: list[str]) -> dict[str, int]:
        return await self._domain.count_workspaces_by_member_ids(user_ids)

    async def user_has_active_membership(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> bool:
        return await self._domain.user_has_active_membership(
            workspace_id=workspace_id,
            user_id=user_id,
        )

    async def update_workspace(self, workspace_id: str, **kwargs: Any) -> Workspace | None:
        return await self._domain.update_workspace(
            workspace_id,
            WorkspaceUpdateCommand(**self._normalize_update_kwargs(kwargs)),
        )

    async def update_loaded_workspace(self, workspace: Workspace, **kwargs: Any) -> Workspace:
        return await self._domain.update_loaded_workspace(
            workspace,
            WorkspaceUpdateCommand(**self._normalize_update_kwargs(kwargs)),
        )

    async def delete_workspace(self, workspace_id: str) -> bool:
        return await self._domain.delete_workspace(workspace_id)

    async def get_workspace_settings(self, workspace_id: str) -> WorkspaceSettingsRecord | None:
        return await self._domain.get_workspace_settings(workspace_id)

    async def get_or_create_workspace_settings(self, workspace_id: str) -> WorkspaceSettingsRecord:
        return await self._domain.get_or_create_workspace_settings(workspace_id)

    async def update_workspace_settings(
        self,
        workspace_id: str,
        **kwargs: Any,
    ) -> WorkspaceSettingsRecord | None:
        return await self._domain.update_workspace_settings(
            workspace_id,
            WorkspaceSettingsUpdateCommand(**kwargs),
        )

    async def delete_workspace_settings(self, workspace_id: str) -> bool:
        return await self._domain.delete_workspace_settings(workspace_id)

    @staticmethod
    def _normalize_update_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(kwargs)
        if "type" in normalized:
            normalized["workspace_type"] = normalize_workspace_type(normalized.pop("type"))
        if "workspace_type" in normalized and normalized["workspace_type"] is not None:
            normalized["workspace_type"] = normalize_workspace_type(normalized["workspace_type"])
        if "config" in normalized:
            normalized["settings_json"] = normalized.pop("config")
        if "thread_id" in normalized:
            normalized["active_thread_id"] = normalized.pop("thread_id")
        return normalized
