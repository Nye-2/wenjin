"""Workspace service for managing academic workspaces.

This service provides workspace management functionality including:
- Workspace CRUD operations
- Workspace configuration handling

Note: Paper association management is handled by PaperService.
"""


from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Workspace, WorkspaceType

_CHAT_ROLLOUT_DEFAULT_TYPES = {
    "thesis",
    "sci",
    "proposal",
    "software_copyright",
    "patent",
}


class WorkspaceService:
    """Service for managing workspaces.

    This class provides CRUD operations for workspaces.
    Paper association management is handled by PaperService.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize WorkspaceService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db: AsyncSession = db

    @staticmethod
    def _with_rollout_defaults(
        workspace_type: WorkspaceType | str,
        config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Inject rollout defaults into workspace.config without overwriting overrides."""
        type_value = workspace_type.value if hasattr(workspace_type, "value") else str(workspace_type)
        base_config = dict(config or {})
        rollout = base_config.get("rollout")
        rollout_config = dict(rollout) if isinstance(rollout, dict) else {}
        enabled_by_default = type_value in _CHAT_ROLLOUT_DEFAULT_TYPES
        rollout_config.setdefault("chat_cockpit_enabled", enabled_by_default)
        rollout_config.setdefault("chat_feature_orchestration_enabled", enabled_by_default)
        base_config["rollout"] = rollout_config
        return base_config

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
        # Convert string to WorkspaceType enum if needed
        if isinstance(type, str):
            try:
                workspace_type = WorkspaceType(type)
            except ValueError:
                valid_types = [t.value for t in WorkspaceType]
                raise ValueError(
                    f"Invalid workspace type: {type}. Must be one of: {valid_types}"
                ) from None
        else:
            workspace_type = type

        workspace = Workspace(
            user_id=user_id,
            name=name,
            type=workspace_type,
            discipline=discipline,
            description=description,
            config=self._with_rollout_defaults(workspace_type, config),
        )
        self.db.add(workspace)
        await self.db.commit()
        await self.db.refresh(workspace)
        return workspace

    async def get(self, workspace_id: str) -> Workspace | None:
        """Get workspace by ID.

        Args:
            workspace_id: Workspace UUID string

        Returns:
            Workspace if found, None otherwise
        """
        result = await self.db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> list[Workspace]:
        """List all workspaces for a user.

        Args:
            user_id: User UUID string

        Returns:
            List of workspaces ordered by most recently updated
        """
        result = await self.db.execute(
            select(Workspace)
            .where(Workspace.user_id == user_id)
            .order_by(Workspace.updated_at.desc())
        )
        return list(result.scalars().all())

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
        if not workspace:
            return None

        # Handle type conversion if provided
        if "type" in kwargs:
            type_value = kwargs["type"]
            if isinstance(type_value, str):
                try:
                    kwargs["type"] = WorkspaceType(type_value)
                except ValueError:
                    valid_types = [t.value for t in WorkspaceType]
                    raise ValueError(
                        f"Invalid workspace type: {type_value}. Must be one of: {valid_types}"
                    ) from None

        # Update only provided fields
        if "config" in kwargs or "type" in kwargs:
            target_type = kwargs.get("type", workspace.type)
            source_config = kwargs.get("config", workspace.config)
            kwargs["config"] = self._with_rollout_defaults(target_type, source_config)

        for key, value in kwargs.items():
            if hasattr(workspace, key):
                setattr(workspace, key, value)

        await self.db.commit()
        await self.db.refresh(workspace)
        return workspace

    async def delete(self, workspace_id: str) -> bool:
        """Delete a workspace.

        This will cascade delete all associated records (papers, artifacts, etc.)

        Args:
            workspace_id: Workspace UUID string

        Returns:
            True if deleted, False if not found
        """
        result = await self.db.execute(
            delete(Workspace).where(Workspace.id == workspace_id)
        )
        await self.db.commit()
        return (result.rowcount or 0) > 0
