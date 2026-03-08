"""Paper service for managing academic literature."""

import hashlib
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, WorkspacePaper, PaperExtraction, PaperChunk


class PaperService:
    """Service for managing academic papers."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create(
        self,
        title: str,
        doi: Optional[str] = None,
        authors: Optional[list[dict]] = None,
        year: Optional[int] = None,
        venue: Optional[str] = None,
        abstract: Optional[str] = None,
        file_path: Optional[str] = None,
        source: str = "manual_upload",
        external_ids: Optional[dict] = None,
        citation_count: Optional[int] = None,
        reference_count: Optional[int] = None,
    ) -> Paper:
        """Create a new paper.

        Args:
            title: Paper title
            doi: Digital Object Identifier
            authors: List of author dicts
            year: Publication year
            venue: Publication venue
            abstract: Paper abstract
            file_path: Path to PDF file
            source: Source of paper data
            external_ids: External identifiers
            citation_count: Citation count
            reference_count: Reference count

        Returns:
            Created paper
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
            file_path=file_path,
            source=source,
            external_ids=external_ids or {},
            citation_count=citation_count,
            reference_count=reference_count,
        )
        self.db.add(paper)
        await self.db.commit()
        await self.db.refresh(paper)
        return paper

    async def get(self, paper_id: str) -> Optional[Paper]:
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

    async def get_by_doi(self, doi: str) -> Optional[Paper]:
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

    async def add_to_workspace(
        self,
        workspace_id: str,
        paper_id: str,
        notes: Optional[str] = None,
        tags: Optional[list[str]] = None,
        is_primary: bool = False,
    ) -> WorkspacePaper:
        """Add paper to workspace.

        Args:
            workspace_id: Workspace ID
            paper_id: Paper ID
            notes: User notes
            tags: User-defined tags
            is_primary: Whether this is a primary reference

        Returns:
            WorkspacePaper association
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
        read_status: Optional[str] = None,
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
        # Simple text search in title and abstract
        result = await self.db.execute(
            select(Paper)
            .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
            .where(WorkspacePaper.workspace_id == workspace_id)
            .where(
                Paper.title.ilike(f"%{query}%") |
                Paper.abstract.ilike(f"%{query}%")
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
        processing_time_ms: Optional[int] = None,
        model_used: Optional[str] = None,
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
        tier: Optional[int] = None,
    ) -> Optional[PaperExtraction]:
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
        workspace_id: str,
        paper_id: str,
    ) -> bool:
        """Remove paper from workspace.

        Args:
            workspace_id: Workspace ID
            paper_id: Paper ID

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
