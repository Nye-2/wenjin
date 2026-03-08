"""Workspace service for managing academic workspaces."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Workspace


class WorkspaceService:
    """Service for managing workspaces."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create(
        self,
        user_id: str,
        name: str,
        type: str,
        discipline: Optional[str] = None,
        description: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> Workspace:
        """Create a new workspace.

        Args:
            user_id: User ID
            name: Workspace name
            type: Workspace type (sci, thesis, proposal, grant)
            discipline: Academic discipline
            description: Workspace description
            config: Workspace configuration

        Returns:
            Created workspace
        """
        workspace = Workspace(
            user_id=user_id,
            name=name,
            type=type,
            discipline=discipline,
            description=description,
            config=config or {},
        )
        self.db.add(workspace)
        await self.db.commit()
        await self.db.refresh(workspace)
        return workspace

    async def get(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID.

        Args:
            workspace_id: Workspace ID

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
            user_id: User ID

        Returns:
            List of workspaces
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
        name: Optional[str] = None,
        discipline: Optional[str] = None,
        description: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> Optional[Workspace]:
        """Update workspace.

        Args:
            workspace_id: Workspace ID
            name: New name
            discipline: New discipline
            description: New description
            config: New configuration

        Returns:
            Updated workspace if found, None otherwise
        """
        workspace = await self.get(workspace_id)
        if not workspace:
            return None

        if name is not None:
            workspace.name = name
        if discipline is not None:
            workspace.discipline = discipline
        if description is not None:
            workspace.description = description
        if config is not None:
            workspace.config = config
        # updated_at is automatically handled by SQLAlchemy onupdate

        await self.db.commit()
        await self.db.refresh(workspace)
        return workspace

    async def delete(self, workspace_id: str) -> bool:
        """Delete workspace.

        Args:
            workspace_id: Workspace ID

        Returns:
            True if deleted, False if not found
        """
        workspace = await self.get(workspace_id)
        if not workspace:
            return False

        await self.db.delete(workspace)
        await self.db.commit()
        return True
