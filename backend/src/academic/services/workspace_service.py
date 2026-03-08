"""Workspace service for managing academic workspaces.

This service provides workspace management functionality including:
- Workspace CRUD operations
- Paper association management
- Workspace configuration handling
"""


from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Workspace, WorkspacePaper, WorkspaceType


class WorkspaceService:
    """Service for managing workspaces.

    This class provides CRUD operations and paper association management
    for workspaces. It requires an AsyncSession for database operations.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(self, db: AsyncSession):
        """Initialize WorkspaceService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create(
        self,
        user_id: str,
        name: str,
        type: str,
        discipline: str | None = None,
        description: str | None = None,
        config: dict | None = None,
    ) -> Workspace:
        """Create a new workspace.

        Args:
            user_id: User ID who owns the workspace
            name: Workspace name
            type: Workspace type (sci, thesis, proposal, grant, literature_review)
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
            config=config or {},
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
        **kwargs,
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
        for key, value in kwargs.items():
            if hasattr(workspace, key) and value is not None:
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
        workspace = await self.get(workspace_id)
        if not workspace:
            return False

        await self.db.delete(workspace)
        await self.db.commit()
        return True

    async def add_paper(
        self,
        workspace_id: str,
        paper_id: str,
        notes: str | None = None,
        tags: list[str] | None = None,
        is_primary: bool = False,
        read_status: str = "unread",
    ) -> WorkspacePaper:
        """Add a paper to a workspace.

        Creates a WorkspacePaper association record linking the paper
        to the workspace with optional metadata.

        Args:
            workspace_id: Workspace UUID string
            paper_id: Paper UUID string
            notes: Optional user notes for this paper
            tags: Optional list of tags for categorization
            is_primary: Whether this is a primary reference paper
            read_status: Reading status (unread, reading, read)

        Returns:
            Created WorkspacePaper association object

        Raises:
            ValueError: If paper is already in workspace
        """
        # Check if paper already exists in workspace
        existing = await self._get_workspace_paper(workspace_id, paper_id)
        if existing:
            raise ValueError(
                f"Paper {paper_id} is already in workspace {workspace_id}"
            )

        workspace_paper = WorkspacePaper(
            workspace_id=workspace_id,
            paper_id=paper_id,
            notes=notes,
            tags=tags or [],
            is_primary=is_primary,
            read_status=read_status,
        )
        self.db.add(workspace_paper)
        await self.db.commit()
        await self.db.refresh(workspace_paper)
        return workspace_paper

    async def remove_paper(self, workspace_id: str, paper_id: str) -> bool:
        """Remove a paper from a workspace.

        Removes the WorkspacePaper association record. The paper itself
        is not deleted from the database.

        Args:
            workspace_id: Workspace UUID string
            paper_id: Paper UUID string

        Returns:
            True if removed, False if not found
        """
        workspace_paper = await self._get_workspace_paper(workspace_id, paper_id)
        if not workspace_paper:
            return False

        await self.db.delete(workspace_paper)
        await self.db.commit()
        return True

    async def _get_workspace_paper(
        self, workspace_id: str, paper_id: str
    ) -> WorkspacePaper | None:
        """Get WorkspacePaper association by workspace and paper IDs.

        Args:
            workspace_id: Workspace UUID string
            paper_id: Paper UUID string

        Returns:
            WorkspacePaper if found, None otherwise
        """
        result = await self.db.execute(
            select(WorkspacePaper).where(
                and_(
                    WorkspacePaper.workspace_id == workspace_id,
                    WorkspacePaper.paper_id == paper_id,
                )
            )
        )
        return result.scalar_one_or_none()
