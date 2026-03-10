# src/academic/literature/navigation/section_loader.py
"""Section content loader."""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import PaperExtraction
from .models import PaperTOC, SectionContent, TOCEntry

logger = logging.getLogger(__name__)


class SectionLoader:
    """Loader for paper section content.

    This service loads specific section content from papers based on
    the TOC structure. It retrieves the full_text from PaperExtraction
    and extracts content based on character positions.
    """

    def __init__(self, db: AsyncSession):
        """Initialize SectionLoader.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def load_section(
        self,
        toc: PaperTOC,
        section_title: str,
    ) -> SectionContent | None:
        """Load content for a specific section.

        Args:
            toc: Paper TOC structure
            section_title: Section title to load

        Returns:
            SectionContent if found, None otherwise
        """
        # Find the entry
        entry = toc.find_entry(section_title)
        if not entry:
            logger.warning(f"Section not found: {section_title}")
            return None

        # Get paper full text from extraction
        result = await self.db.execute(
            select(PaperExtraction.structured_data)
            .where(PaperExtraction.paper_id == toc.paper_id)
            .where(PaperExtraction.extraction_type == "full_text")
            .order_by(PaperExtraction.tier.desc(), PaperExtraction.created_at.desc())
            .limit(1)
        )
        structured_data = result.scalar_one_or_none()

        if not structured_data:
            logger.warning(f"Paper text not found: {toc.paper_id}")
            return None

        full_text = structured_data.get("full_text", "")
        if not full_text:
            logger.warning(f"Full text empty for paper: {toc.paper_id}")
            return None

        # Extract section content
        content = full_text[entry.char_start:entry.char_end]

        return SectionContent(
            paper_id=toc.paper_id,
            section_title=entry.title,
            content=content.strip(),
            word_count=len(content.split()),
            has_subsections=len(entry.children) > 0,
        )

    async def get_abstract(self, toc: PaperTOC) -> SectionContent:
        """Get paper abstract.

        The abstract is always available without loading from DB.

        Args:
            toc: Paper TOC structure

        Returns:
            SectionContent for abstract
        """
        return SectionContent(
            paper_id=toc.paper_id,
            section_title="Abstract",
            content=toc.abstract,
            word_count=len(toc.abstract.split()),
            has_subsections=False,
        )
