"""Paper service for managing academic literature.

This service provides paper management functionality including:
- Paper CRUD operations
- Search across title, authors, and abstract
- Workspace-paper association management
"""


from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, PaperExtraction, WorkspacePaper


class PaperService:
    """Service for managing academic papers.

    This class provides CRUD operations and workspace association management
    for papers. It requires an AsyncSession for database operations.

    Attributes:
        db: AsyncSession for database operations
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create(
        self,
        title: str,
        authors: list[dict],
        doi: str | None = None,
        year: int | None = None,
        venue: str | None = None,
        abstract: str | None = None,
        source: str = "manual_upload",
        source_url: str | None = None,
    ) -> Paper:
        """Create a new paper.

        Args:
            title: Paper title
            authors: List of author dicts with 'name' and optionally 'affiliation'
            doi: Digital Object Identifier (optional)
            year: Publication year (optional)
            venue: Publication venue (optional)
            abstract: Paper abstract (optional)
            source: Source of paper data (default: "manual_upload")
            source_url: External source URL (optional)

        Returns:
            Created paper object

        Raises:
            IntegrityError: If DOI already exists
        """
        # Check if paper with same DOI exists
        if doi:
            existing = await self.get_by_doi(doi)
            if existing:
                return existing

        paper = Paper(
            doi=doi,
            title=title,
            authors=authors or [],
            year=year,
            venue=venue,
            abstract=abstract,
            source=source,
            source_url=source_url,
        )
        self.db.add(paper)
        await self.db.commit()
        await self.db.refresh(paper)
        return paper

    async def get(self, paper_id: str) -> Paper | None:
        """Get paper by ID.

        Args:
            paper_id: Paper ID

        Returns:
            Paper if found, None otherwise
        """
        result = await self.db.execute(
            select(Paper).where(Paper.id == paper_id)
        )
        return result.scalar_one_or_none()

    async def get_by_doi(self, doi: str) -> Paper | None:
        """Get paper by DOI.

        Args:
            doi: Digital Object Identifier

        Returns:
            Paper if found, None otherwise
        """
        result = await self.db.execute(
            select(Paper).where(Paper.doi == doi)
        )
        return result.scalar_one_or_none()

    async def update(self, paper_id: str, **kwargs) -> Paper | None:
        """Update paper fields.

        Args:
            paper_id: Paper UUID string
            **kwargs: Fields to update (title, authors, year, venue, abstract, etc.)

        Returns:
            Updated paper if found, None otherwise
        """
        paper = await self.get(paper_id)
        if not paper:
            return None

        # Update only provided fields
        for key, value in kwargs.items():
            if hasattr(paper, key) and value is not None:
                setattr(paper, key, value)

        await self.db.commit()
        await self.db.refresh(paper)
        return paper

    async def delete(self, paper_id: str) -> bool:
        """Delete a paper.

        This will cascade delete all associated records (workspace associations,
        extractions, chunks, sections).

        Args:
            paper_id: Paper UUID string

        Returns:
            True if deleted, False if not found
        """
        paper = await self.get(paper_id)
        if not paper:
            return False

        await self.db.delete(paper)
        await self.db.commit()
        return True

    async def search(
        self,
        query: str,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[Paper]:
        """Search papers by title, authors, or abstract.

        Performs a case-insensitive search across paper title, abstract,
        and author names. Optionally filters by workspace.

        Args:
            query: Search query string
            workspace_id: Optional workspace UUID to filter results
            limit: Maximum number of results to return (default: 20)

        Returns:
            List of matching papers
        """
        # Build base query
        if workspace_id:
            base_query = (
                select(Paper)
                .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
                .where(WorkspacePaper.workspace_id == workspace_id)
            )
        else:
            base_query = select(Paper)

        # Add search conditions - search in title, abstract
        # Escape LIKE special characters to prevent SQL injection
        escaped_query = query.replace("%", "\\%").replace("_", "\\_")
        search_condition = or_(
            Paper.title.ilike(f"%{escaped_query}%", escape="\\"),
            Paper.abstract.ilike(f"%{escaped_query}%", escape="\\"),
        )

        query_stmt = base_query.where(search_condition).limit(limit)

        result = await self.db.execute(query_stmt)
        return list(result.scalars().all())

    async def add_to_workspace(
        self,
        paper_id: str,
        workspace_id: str,
        notes: str | None = None,
        tags: list[str] | None = None,
        is_primary: bool = False,
    ) -> WorkspacePaper:
        """Add paper to workspace with metadata.

        Creates a WorkspacePaper association record linking the paper
        to the workspace with optional metadata.

        Args:
            paper_id: Paper UUID string
            workspace_id: Workspace UUID string
            notes: Optional user notes for this paper
            tags: Optional list of tags for categorization
            is_primary: Whether this is a primary reference paper

        Returns:
            Created or existing WorkspacePaper association object
        """
        # Check if already added
        result = await self.db.execute(
            select(WorkspacePaper).where(
                WorkspacePaper.workspace_id == workspace_id,
                WorkspacePaper.paper_id == paper_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        workspace_paper = WorkspacePaper(
            workspace_id=workspace_id,
            paper_id=paper_id,
            notes=notes,
            tags=tags or [],
            is_primary=is_primary,
        )
        self.db.add(workspace_paper)
        await self.db.commit()
        await self.db.refresh(workspace_paper)
        return workspace_paper

    async def list_workspace_papers(
        self,
        workspace_id: str,
        read_status: str | None = None,
    ) -> list[Paper]:
        """List papers in a workspace.

        Args:
            workspace_id: Workspace ID
            read_status: Filter by read status (optional)

        Returns:
            List of papers
        """
        query = (
            select(Paper)
            .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
            .where(WorkspacePaper.workspace_id == workspace_id)
        )
        if read_status:
            query = query.where(WorkspacePaper.read_status == read_status)
        query = query.order_by(WorkspacePaper.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search_in_workspace(
        self,
        workspace_id: str,
        query: str,
        limit: int = 10,
    ) -> list[Paper]:
        """Search papers in workspace.

        Args:
            workspace_id: Workspace ID
            query: Search query
            limit: Maximum results

        Returns:
            List of matching papers
        """
        # Escape LIKE special characters to prevent SQL injection
        escaped_query = query.replace("%", "\\%").replace("_", "\\_")

        # Simple text search in title and abstract
        result = await self.db.execute(
            select(Paper)
            .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
            .where(WorkspacePaper.workspace_id == workspace_id)
            .where(
                Paper.title.ilike(f"%{escaped_query}%", escape="\\") |
                Paper.abstract.ilike(f"%{escaped_query}%", escape="\\")
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def store_extraction(
        self,
        paper_id: str,
        tier: int,
        extraction_type: str,
        structured_data: dict,
        processing_time_ms: int | None = None,
        model_used: str | None = None,
    ) -> PaperExtraction:
        """Store paper extraction result.

        Args:
            paper_id: Paper ID
            tier: Extraction tier (1=engineering, 2=LLM)
            extraction_type: Type of extraction
            structured_data: Extracted data
            processing_time_ms: Processing time in milliseconds
            model_used: LLM model used (for tier 2)

        Returns:
            PaperExtraction record
        """
        extraction = PaperExtraction(
            paper_id=paper_id,
            tier=tier,
            extraction_type=extraction_type,
            structured_data=structured_data,
            processing_time_ms=processing_time_ms,
            model_used=model_used,
        )
        self.db.add(extraction)
        await self.db.commit()
        await self.db.refresh(extraction)
        return extraction

    async def get_extraction(
        self,
        paper_id: str,
        tier: int | None = None,
    ) -> PaperExtraction | None:
        """Get paper extraction result.

        Args:
            paper_id: Paper ID
            tier: Extraction tier (optional)

        Returns:
            Latest extraction if found
        """
        query = select(PaperExtraction).where(
            PaperExtraction.paper_id == paper_id
        )
        if tier:
            query = query.where(PaperExtraction.tier == tier)
        query = query.order_by(PaperExtraction.created_at.desc())

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def remove_from_workspace(
        self,
        paper_id: str,
        workspace_id: str,
    ) -> bool:
        """Remove paper from workspace.

        Removes the WorkspacePaper association record. The paper itself
        is not deleted from the database.

        Args:
            paper_id: Paper UUID string
            workspace_id: Workspace UUID string

        Returns:
            True if removed, False if not found
        """
        result = await self.db.execute(
            select(WorkspacePaper).where(
                WorkspacePaper.workspace_id == workspace_id,
                WorkspacePaper.paper_id == paper_id,
            )
        )
        workspace_paper = result.scalar_one_or_none()
        if not workspace_paper:
            return False

        await self.db.delete(workspace_paper)
        await self.db.commit()
        return True
