"""Literature service for managing workspace literature references.

This service provides literature management functionality including:
- Listing literature with filters
- Creating literature entries
- Batch importing literature
- Updating literature metadata
- Deleting literature
- Counting literature
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import WorkspaceLiterature


class LiteratureService:
    """Service for managing workspace literature.

    This class provides CRUD operations for literature entries within a workspace.
    It requires an AsyncSession for database operations.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(self, db: AsyncSession):
        """Initialize LiteratureService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def list_literature(
        self,
        workspace_id: str,
        source: str | None = None,
        is_core: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List literature entries for a workspace with optional filters.

        Args:
            workspace_id: UUID of the workspace
            source: Optional filter by source (manual, deep_research, etc.)
            is_core: Optional filter by core reference status
            offset: Number of items to skip
            limit: Maximum number of items to return

        Returns:
            Dictionary with items, total count, and core count
        """
        # Build base query
        base_query = select(WorkspaceLiterature).where(
            WorkspaceLiterature.workspace_id == workspace_id
        )

        # Apply filters
        if source is not None:
            base_query = base_query.where(WorkspaceLiterature.source == source)
        if is_core is not None:
            base_query = base_query.where(WorkspaceLiterature.is_core == is_core)

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Get core count
        core_query = select(func.count()).where(
            WorkspaceLiterature.workspace_id == workspace_id,
            WorkspaceLiterature.is_core == True,  # noqa: E712
        )
        core_result = await self.db.execute(core_query)
        core_count = core_result.scalar() or 0

        # Get paginated items
        items_query = base_query.order_by(WorkspaceLiterature.created_at.desc())
        items_query = items_query.offset(offset).limit(limit)
        items_result = await self.db.execute(items_query)
        items = items_result.scalars().all()

        return {
            "items": [self._to_dict(item) for item in items],
            "total": total,
            "core_count": core_count,
        }

    async def create_literature(
        self,
        workspace_id: str,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
        citations: int | None = None,
        venue: str | None = None,
        quartile: str | None = None,
        abstract: str | None = None,
        doi: str | None = None,
        source: str = "manual",
        is_core: bool = False,
    ) -> dict[str, Any]:
        """Create a new literature entry.

        Args:
            workspace_id: UUID of the workspace
            title: Title of the literature
            authors: List of author names
            year: Publication year
            citations: Number of citations
            venue: Publication venue
            quartile: Journal quartile (Q1, Q2, Q3, Q4)
            abstract: Abstract or summary
            doi: Digital Object Identifier
            source: Source of the literature (default: manual)
            is_core: Whether this is a core reference

        Returns:
            Created literature entry as dictionary
        """
        literature = WorkspaceLiterature(
            workspace_id=workspace_id,
            title=title,
            authors=authors or [],
            year=year,
            citations=citations,
            venue=venue,
            quartile=quartile,
            abstract=abstract,
            doi=doi,
            source=source,
            is_core=is_core,
        )

        self.db.add(literature)
        await self.db.commit()
        await self.db.refresh(literature)

        return self._to_dict(literature)

    async def batch_import(
        self,
        workspace_id: str,
        source: str,
        paper_ids: list[str],
    ) -> dict[str, Any]:
        """Batch import literature entries.

        This is a placeholder implementation that returns the count.
        In a real implementation, this would fetch paper details from
        the source (e.g., deep_research) and create literature entries.

        Args:
            workspace_id: UUID of the workspace
            source: Source of the papers (e.g., deep_research)
            paper_ids: List of paper identifiers to import

        Returns:
            Dictionary with imported count
        """
        # Placeholder implementation
        # In production, this would:
        # 1. Fetch paper details from the source
        # 2. Create WorkspaceLiterature entries for each
        # 3. Return the count of successfully imported papers

        # For now, just return the count
        return {"imported": len(paper_ids)}

    async def update_literature(
        self,
        literature_id: str,
        **kwargs,
    ) -> dict[str, Any] | None:
        """Update a literature entry.

        Args:
            literature_id: UUID of the literature entry
            **kwargs: Fields to update (is_core, title, authors, etc.)

        Returns:
            Updated literature entry as dictionary, or None if not found
        """
        result = await self.db.execute(
            select(WorkspaceLiterature).where(WorkspaceLiterature.id == literature_id)
        )
        literature = result.scalar_one_or_none()

        if literature is None:
            return None

        # Update allowed fields
        allowed_fields = {
            "title", "authors", "year", "citations", "venue",
            "quartile", "abstract", "doi", "source", "is_core",
        }

        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(literature, key, value)

        await self.db.commit()
        await self.db.refresh(literature)

        return self._to_dict(literature)

    async def delete_literature(self, literature_id: str) -> bool:
        """Delete a literature entry.

        Args:
            literature_id: UUID of the literature entry

        Returns:
            True if deleted, False if not found
        """
        result = await self.db.execute(
            select(WorkspaceLiterature).where(WorkspaceLiterature.id == literature_id)
        )
        literature = result.scalar_one_or_none()

        if literature is None:
            return False

        await self.db.delete(literature)
        await self.db.commit()

        return True

    async def count_literature(self, workspace_id: str) -> dict[str, int]:
        """Count literature entries for a workspace.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            Dictionary with total and core counts
        """
        # Get total count
        total_query = select(func.count()).where(
            WorkspaceLiterature.workspace_id == workspace_id
        )
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        # Get core count
        core_query = select(func.count()).where(
            WorkspaceLiterature.workspace_id == workspace_id,
            WorkspaceLiterature.is_core == True,  # noqa: E712
        )
        core_result = await self.db.execute(core_query)
        core = core_result.scalar() or 0

        return {"total": total, "core": core}

    def _to_dict(self, literature: WorkspaceLiterature) -> dict[str, Any]:
        """Convert WorkspaceLiterature ORM object to dictionary.

        Args:
            literature: WorkspaceLiterature ORM object

        Returns:
            Dictionary representation
        """
        return {
            "id": str(literature.id),
            "workspace_id": str(literature.workspace_id),
            "title": literature.title,
            "authors": literature.authors or [],
            "year": literature.year,
            "citations": literature.citations,
            "venue": literature.venue,
            "quartile": literature.quartile,
            "abstract": literature.abstract,
            "doi": literature.doi,
            "source": literature.source,
            "is_core": literature.is_core,
            "created_at": literature.created_at.isoformat() if literature.created_at else None,
            "updated_at": literature.updated_at.isoformat() if literature.updated_at else None,
        }


async def get_literature_service() -> LiteratureService:
    """Get LiteratureService instance for dependency injection.

    This is a placeholder that will be overridden in the router.
    The actual implementation requires a database session.

    Returns:
        LiteratureService instance
    """
    raise NotImplementedError("This should be overridden via dependency_overrides")
