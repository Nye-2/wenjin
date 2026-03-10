"""Citation service for managing paper citation relationships."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Citation, CitationType


class CitationService:
    """Service for managing citations."""

    def __init__(self, db: AsyncSession):
        """Initialize CitationService with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def add_citation(
        self,
        paper_id: str,
        cited_paper_id: str,
        workspace_id: str,
        citation_context: str | None = None,
        section: str | None = None,
        page_number: int | None = None,
        citation_type: str = CitationType.EXPLICIT,
    ) -> Citation:
        """Add citation relationship.

        Args:
            paper_id: Source paper ID (the one that cites)
            cited_paper_id: Target paper ID (the one being cited)
            workspace_id: Workspace context
            citation_context: Text surrounding the citation
            section: Section where citation appears
            page_number: Page number in source paper
            citation_type: Type of citation

        Returns:
            Created Citation object
        """
        citation = Citation(
            paper_id=paper_id,
            cited_paper_id=cited_paper_id,
            workspace_id=workspace_id,
            citation_context=citation_context,
            section=section,
            page_number=page_number,
            citation_type=citation_type,
        )
        self.db.add(citation)
        await self.db.commit()
        await self.db.refresh(citation)
        return citation

    async def get_outgoing_citations(
        self,
        paper_id: str,
        workspace_id: str,
    ) -> list[Citation]:
        """Get papers cited by this paper.

        Args:
            paper_id: Paper ID to get citations for
            workspace_id: Workspace context

        Returns:
            List of Citation objects
        """
        result = await self.db.execute(
            select(Citation).where(
                Citation.paper_id == paper_id,
                Citation.workspace_id == workspace_id,
            )
        )
        return list(result.scalars().all())

    async def get_incoming_citations(
        self,
        paper_id: str,
        workspace_id: str,
    ) -> list[Citation]:
        """Get papers that cite this paper.

        Args:
            paper_id: Paper ID to get citations for
            workspace_id: Workspace context

        Returns:
            List of Citation objects
        """
        result = await self.db.execute(
            select(Citation).where(
                Citation.cited_paper_id == paper_id,
                Citation.workspace_id == workspace_id,
            )
        )
        return list(result.scalars().all())

    async def remove_citation(
        self,
        paper_id: str,
        cited_paper_id: str,
        workspace_id: str,
    ) -> bool:
        """Remove citation relationship.

        Args:
            paper_id: Source paper ID
            cited_paper_id: Target paper ID
            workspace_id: Workspace context

        Returns:
            True if removed, False if not found
        """
        result = await self.db.execute(
            select(Citation).where(
                Citation.paper_id == paper_id,
                Citation.cited_paper_id == cited_paper_id,
                Citation.workspace_id == workspace_id,
            )
        )
        citation = result.scalar_one_or_none()

        if not citation:
            return False

        await self.db.delete(citation)
        await self.db.commit()
        return True
