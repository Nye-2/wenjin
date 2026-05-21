"""Workspace service for managing academic workspaces.

This service provides workspace management functionality including:
- Workspace CRUD operations
- Workspace configuration handling

Note: Workspace-scoped references are handled by the Reference Library services.
"""


from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.workspace_api import WorkspaceDataService

if TYPE_CHECKING:
    from src.database import Workspace, WorkspaceType


class WorkspaceService:
    """Service for managing workspaces.

    This class provides CRUD operations for workspaces.
    Reference-library management is handled by dedicated reference services.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize WorkspaceService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db: AsyncSession = db
        self._dataservice = WorkspaceDataService(db)

    @staticmethod
    def _with_rollout_defaults(
        workspace_type: WorkspaceType | str,
        config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Inject rollout defaults into workspace settings without overwriting overrides."""
        return WorkspaceDataService.with_rollout_defaults(workspace_type, config)

    async def create(
        self,
        user_id: str,
        name: str,
        type: str,
        discipline: str | None = None,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> Workspace:
        """Create a new workspace.

        Args:
            user_id: User ID who owns the workspace
            name: Workspace name
            type: Workspace type (sci, thesis, proposal, software_copyright, patent)
            discipline: Academic discipline (e.g., computer_science)
            description: Workspace description
            config: Workspace configuration as JSON

        Returns:
            Created workspace object

        Raises:
            ValueError: If type is not a valid WorkspaceType
        """
        return await self._dataservice.create_workspace(
            created_by_user_id=user_id,
            name=name,
            workspace_type=type,
            discipline=discipline,
            description=description,
            settings_json=config or {},
        )

    async def get(self, workspace_id: str) -> Workspace | None:
        """Get workspace by ID.

        Args:
            workspace_id: Workspace UUID string

        Returns:
            Workspace if found, None otherwise
        """
        return await self._dataservice.get_workspace(workspace_id)

    async def list_by_user(self, user_id: str) -> list[Workspace]:
        """List all workspaces for a user.

        Args:
            user_id: User UUID string

        Returns:
            List of workspaces ordered by most recently updated
        """
        return await self._dataservice.list_workspaces_for_member(user_id)

    async def has_active_membership(self, *, workspace_id: str, user_id: str) -> bool:
        """Return whether a user can access a workspace."""
        return await self._dataservice.user_has_active_membership(
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
            **kwargs: Fields to update (name, discipline, description, config)

        Returns:
            Updated workspace if found, None otherwise

        Raises:
            ValueError: If type is provided and not a valid WorkspaceType
        """
        workspace = await self.get(workspace_id)
        if workspace is None:
            return None
        return await self._dataservice.update_loaded_workspace(workspace, **kwargs)

    async def delete(self, workspace_id: str) -> bool:
        """Delete a workspace.

        This will cascade delete all associated records (references, artifacts, etc.)

        Args:
            workspace_id: Workspace UUID string

        Returns:
            True if deleted, False if not found
        """
        return await self._dataservice.delete_workspace(workspace_id)
