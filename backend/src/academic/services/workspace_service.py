"""Workspace service for managing academic workspaces.

This service provides workspace management functionality including:
- Workspace CRUD operations
- Workspace configuration handling

Note: Workspace-scoped references are handled by the Reference Library services.
"""


from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.workspace import (
    WorkspaceCreatePayload,
    WorkspaceUpdatePayload,
    normalize_workspace_type,
    with_rollout_defaults,
)
from src.dataservice_client.provider import dataservice_client

if TYPE_CHECKING:
    from src.database import Workspace, WorkspaceType


class WorkspaceService:
    """Service for managing workspaces.

    This class provides CRUD operations for workspaces.
    Reference-library management is handled by dedicated reference services.

    DataService owns persistence; this facade only adapts workspace application
    code to the DataService client contract.
    """

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        """Initialize WorkspaceService."""
        self._dataservice = dataservice

    @staticmethod
    def _with_rollout_defaults(
        workspace_type: WorkspaceType | str,
        config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Inject rollout defaults into workspace settings without overwriting overrides."""
        return with_rollout_defaults(workspace_type, config)

    async def create(
        self,
        user_id: str,
        name: str,
        type: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> Workspace:
        """Create a new workspace.

        Args:
            user_id: User ID who owns the workspace
            name: Workspace name
            type: Workspace type (sci, thesis, proposal, software_copyright, patent)
            description: Workspace description
            config: Workspace configuration as JSON

        Returns:
            Created workspace object

        Raises:
            ValueError: If type is not a valid WorkspaceType
        """
        command = WorkspaceCreatePayload(
            created_by_user_id=user_id,
            name=name,
            workspace_type=normalize_workspace_type(type),
            description=description,
            settings_json=config or {},
        )
        if self._dataservice is not None:
            return await self._dataservice.create_workspace(command)
        async with dataservice_client() as client:
            return await client.create_workspace(command)

    async def get(self, workspace_id: str) -> Workspace | None:
        """Get workspace by ID.

        Args:
            workspace_id: Workspace UUID string

        Returns:
            Workspace if found, None otherwise
        """
        if self._dataservice is not None:
            return await self._dataservice.get_workspace(workspace_id)
        async with dataservice_client() as client:
            return await client.get_workspace(workspace_id)

    async def list_by_user(self, user_id: str) -> list[Workspace]:
        """List all workspaces for a user.

        Args:
            user_id: User UUID string

        Returns:
            List of workspaces ordered by most recently updated
        """
        if self._dataservice is not None:
            return await self._dataservice.list_workspaces(member_user_id=user_id)
        async with dataservice_client() as client:
            return await client.list_workspaces(member_user_id=user_id)

    async def has_active_membership(self, *, workspace_id: str, user_id: str) -> bool:
        """Return whether a user can access a workspace."""
        if self._dataservice is not None:
            return await self._dataservice.workspace_has_active_membership(
                workspace_id=workspace_id,
                user_id=user_id,
            )
        async with dataservice_client() as client:
            return await client.workspace_has_active_membership(
                workspace_id=workspace_id,
                user_id=user_id,
            )

    async def update(
        self,
        workspace_id: str,
        **kwargs: Any,
    ) -> Workspace | None:
        """Update workspace fields.

        Args:
            workspace_id: Workspace UUID string
            **kwargs: Fields to update (name, description, config)

        Returns:
            Updated workspace if found, None otherwise

        Raises:
            ValueError: If type is provided and not a valid WorkspaceType
        """
        command_values: dict[str, Any] = {}
        if "name" in kwargs:
            command_values["name"] = kwargs["name"]
        if "type" in kwargs or "workspace_type" in kwargs:
            command_values["workspace_type"] = normalize_workspace_type(
                kwargs.get("type") or kwargs.get("workspace_type")
            )
        if "description" in kwargs:
            command_values["description"] = kwargs["description"]
        if "config" in kwargs or "settings_json" in kwargs:
            command_values["settings_json"] = kwargs.get("config", kwargs.get("settings_json"))
        if "active_thread_id" in kwargs:
            command_values["active_thread_id"] = kwargs["active_thread_id"]
        command = WorkspaceUpdatePayload(**command_values)
        if self._dataservice is not None:
            return await self._dataservice.update_workspace(workspace_id, command)
        async with dataservice_client() as client:
            return await client.update_workspace(workspace_id, command)

    async def delete(self, workspace_id: str) -> bool:
        """Delete a workspace.

        This will cascade delete all associated records (references, artifacts, etc.)

        Args:
            workspace_id: Workspace UUID string

        Returns:
            True if deleted, False if not found
        """
        if self._dataservice is not None:
            return await self._dataservice.delete_workspace(workspace_id)
        async with dataservice_client() as client:
            return await client.delete_workspace(workspace_id)
