"""Artifact service for managing academic artifacts.

This service provides artifact management functionality including:
- Artifact CRUD operations
- Artifact filtering and listing
- Artifact lineage tracking
"""


from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Artifact, ArtifactType


class ArtifactService:
    """Service for managing academic artifacts.

    This class provides CRUD operations for academic artifacts (research ideas,
    methodologies, frameworks, etc.). It requires an AsyncSession for database
    operations.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(self, db: AsyncSession):
        """Initialize ArtifactService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create(
        self,
        workspace_id: str,
        type: str,
        content: dict,
        title: str | None = None,
        created_by_skill: str | None = None,
        parent_artifact_id: str | None = None,
    ) -> Artifact:
        """Create a new artifact.

        Args:
            workspace_id: Workspace UUID string
            type: Artifact type (research_idea, methodology, etc.)
            content: Artifact content as a dictionary
            title: Optional title for the artifact
            created_by_skill: Name of the skill that created this artifact
            parent_artifact_id: Optional parent artifact ID for derived artifacts

        Returns:
            Created artifact object

        Raises:
            ValueError: If type is not a valid ArtifactType
        """
        # Validate artifact type if it's a string
        if isinstance(type, str):
            try:
                ArtifactType(type)
            except ValueError:
                valid_types = [t.value for t in ArtifactType]
                raise ValueError(
                    f"Invalid artifact type: {type}. Must be one of: {valid_types}"
                )

        artifact = Artifact(
            workspace_id=workspace_id,
            type=type,
            title=title,
            content=content,
            created_by_skill=created_by_skill,
            parent_artifact_id=parent_artifact_id,
            status="draft",
            version=1,
        )
        self.db.add(artifact)
        await self.db.commit()
        await self.db.refresh(artifact)
        return artifact

    async def get(self, artifact_id: str) -> Artifact | None:
        """Get artifact by ID.

        Args:
            artifact_id: Artifact UUID string

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
        type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Artifact]:
        """List artifacts in workspace with optional filtering.

        Args:
            workspace_id: Workspace UUID string
            type: Optional filter by artifact type
            status: Optional filter by status (draft, review, final)
            limit: Maximum number of results (default 50)
            offset: Number of results to skip (default 0)

        Returns:
            List of artifacts ordered by creation date (newest first)
        """
        conditions = [Artifact.workspace_id == workspace_id]

        if type:
            conditions.append(Artifact.type == type)
        if status:
            conditions.append(Artifact.status == status)

        query = (
            select(Artifact)
            .where(and_(*conditions))
            .order_by(Artifact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(self, artifact_id: str, **kwargs) -> Artifact | None:
        """Update artifact fields.

        Args:
            artifact_id: Artifact UUID string
            **kwargs: Fields to update (title, content, status, type, version)

        Returns:
            Updated artifact if found, None otherwise

        Raises:
            ValueError: If type is provided and not a valid ArtifactType
        """
        artifact = await self.get(artifact_id)
        if not artifact:
            return None

        # Validate artifact type if provided
        if "type" in kwargs:
            type_value = kwargs["type"]
            if isinstance(type_value, str):
                try:
                    ArtifactType(type_value)
                except ValueError:
                    valid_types = [t.value for t in ArtifactType]
                    raise ValueError(
                        f"Invalid artifact type: {type_value}. Must be one of: {valid_types}"
                    )

        # Update only provided fields that exist on the model
        valid_fields = {"title", "content", "status", "type", "version", "parent_artifact_id"}
        for key, value in kwargs.items():
            if key in valid_fields and value is not None:
                setattr(artifact, key, value)

        await self.db.commit()
        await self.db.refresh(artifact)
        return artifact

    async def delete(self, artifact_id: str) -> bool:
        """Delete an artifact.

        Args:
            artifact_id: Artifact UUID string

        Returns:
            True if deleted, False if not found
        """
        artifact = await self.get(artifact_id)
        if not artifact:
            return False

        await self.db.delete(artifact)
        await self.db.commit()
        return True

    async def list_by_type(
        self,
        workspace_id: str,
        artifact_type: str,
    ) -> list[Artifact]:
        """List artifacts by type in workspace.

        Args:
            workspace_id: Workspace UUID string
            artifact_type: Type of artifacts to filter by

        Returns:
            List of artifacts of the specified type, ordered by creation date
        """
        result = await self.db.execute(
            select(Artifact)
            .where(
                and_(
                    Artifact.workspace_id == workspace_id,
                    Artifact.type == artifact_type,
                )
            )
            .order_by(Artifact.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_lineage(self, artifact_id: str) -> list[Artifact]:
        """Get artifact lineage (parent chain).

        Traces the ancestry of an artifact from the root (oldest ancestor)
        to the specified artifact.

        Args:
            artifact_id: Artifact UUID string

        Returns:
            List of artifacts from root to the specified artifact.
            Returns empty list if artifact not found.
        """
        lineage = []
        current = await self.get(artifact_id)

        if not current:
            return []

        # Build lineage by walking up the parent chain
        while current:
            lineage.append(current)
            if current.parent_artifact_id:
                current = await self.get(current.parent_artifact_id)
            else:
                break

        # Return from root to current (reverse order)
        return list(reversed(lineage))
