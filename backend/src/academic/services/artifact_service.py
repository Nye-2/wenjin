"""Artifact service for managing academic artifacts."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Artifact


class ArtifactService:
    """Service for managing academic artifacts."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create(
        self,
        workspace_id: str,
        type: str,
        content: dict,
        title: Optional[str] = None,
        created_by_skill: Optional[str] = None,
        parent_artifact_id: Optional[str] = None,
        status: str = "draft",
    ) -> Artifact:
        """Create a new artifact.

        Args:
            workspace_id: Workspace ID
            type: Artifact type (research_idea, methodology, etc.)
            content: Artifact content
            title: Artifact title
            created_by_skill: Name of skill that created this
            parent_artifact_id: Parent artifact ID for derived artifacts
            status: Artifact status (draft, published, archived)

        Returns:
            Created artifact
        """
        artifact = Artifact(
            workspace_id=workspace_id,
            type=type,
            title=title,
            content=content,
            created_by_skill=created_by_skill,
            parent_artifact_id=parent_artifact_id,
            status=status,
        )
        self.db.add(artifact)
        await self.db.commit()
        await self.db.refresh(artifact)
        return artifact

    async def get(self, artifact_id: str) -> Optional[Artifact]:
        """Get artifact by ID.

        Args:
            artifact_id: Artifact ID

        Returns:
            Artifact if found, None otherwise
        """
        result = await self.db.execute(
            select(Artifact).where(Artifact.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(
        self,
        workspace_id: str,
        type: Optional[str] = None,
    ) -> list[Artifact]:
        """List artifacts in a workspace.

        Args:
            workspace_id: Workspace ID
            type: Filter by type (optional)

        Returns:
            List of artifacts
        """
        query = select(Artifact).where(Artifact.workspace_id == workspace_id)
        if type:
            query = query.where(Artifact.type == type)
        query = query.order_by(Artifact.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        artifact_id: str,
        content: Optional[dict] = None,
        title: Optional[str] = None,
        status: Optional[str] = None,
        increment_version: bool = False,
    ) -> Optional[Artifact]:
        """Update artifact content.

        Args:
            artifact_id: Artifact ID
            content: New content
            title: New title
            status: New status
            increment_version: Whether to increment version number

        Returns:
            Updated artifact if found, None otherwise
        """
        artifact = await self.get(artifact_id)
        if not artifact:
            return None

        if content is not None:
            artifact.content = content
        if title is not None:
            artifact.title = title
        if status is not None:
            artifact.status = status
        if increment_version:
            artifact.version = (artifact.version or 1) + 1
        # updated_at is automatically handled by SQLAlchemy onupdate

        await self.db.commit()
        await self.db.refresh(artifact)
        return artifact

    async def delete(self, artifact_id: str) -> bool:
        """Delete artifact.

        Args:
            artifact_id: Artifact ID

        Returns:
            True if deleted, False if not found
        """
        artifact = await self.get(artifact_id)
        if not artifact:
            return False

        await self.db.delete(artifact)
        await self.db.commit()
        return True

    async def get_lineage(self, artifact_id: str) -> list[Artifact]:
        """Get artifact lineage (parent chain).

        Args:
            artifact_id: Artifact ID

        Returns:
            List of artifacts from root to this artifact
        """
        lineage = []
        current = await self.get(artifact_id)

        while current:
            lineage.append(current)
            if current.parent_artifact_id:
                current = await self.get(current.parent_artifact_id)
            else:
                break

        return list(reversed(lineage))
