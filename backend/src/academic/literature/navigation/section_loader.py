# src/academic/literature/navigation/section_loader.py
"""Section content loader with optional Redis caching."""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import PaperExtraction

from .models import PaperTOC, SectionContent, TOCEntry

logger = logging.getLogger(__name__)

# Cache TTL for section content (1 hour)
_SECTION_CACHE_TTL = 3600


class SectionLoader:
    """Loader for paper section content.

    This service loads specific section content from papers based on
    the TOC structure. It retrieves the full_text from PaperExtraction
    and extracts content based on character positions.

    Supports optional Redis caching to avoid repeated DB queries.
    """

    def __init__(self, db: AsyncSession, redis_client=None):
        """Initialize SectionLoader.

        Args:
            db: AsyncSession for database operations
            redis_client: Optional RedisClient for caching
        """
        self.db = db
        self._redis = redis_client

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

        return await self._load_with_cache(toc, entry)

    async def load_section_by_entry(
        self,
        toc: PaperTOC,
        entry: TOCEntry,
    ) -> SectionContent | None:
        """Load content for a specific TOC entry.

        Args:
            toc: Paper TOC structure
            entry: TOC entry to load content for

        Returns:
            SectionContent if found, None otherwise
        """
        return await self._load_with_cache(toc, entry)

    async def _load_with_cache(
        self,
        toc: PaperTOC,
        entry: TOCEntry,
    ) -> SectionContent | None:
        """Load section content with optional Redis caching.

        Args:
            toc: Paper TOC structure
            entry: TOC entry to load content for

        Returns:
            SectionContent if found, None otherwise
        """
        cache_key = (
            f"section:{toc.paper_id}:{entry.char_start}:{entry.char_end}:{entry.title}"
        )

        # Try cache first
        if self._redis:
            try:
                cached = await self._redis.client.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    return SectionContent(**data)
            except Exception:
                logger.debug("Redis cache miss for %s", cache_key)

        # Load from DB
        result = await self.db.execute(
            select(PaperExtraction.structured_data)
            .where(PaperExtraction.paper_id == toc.paper_id)
            .where(PaperExtraction.extraction_type == "full_text")
            .order_by(PaperExtraction.tier.desc(), PaperExtraction.created_at.desc())
            .limit(1)
        )
        structured_data = result.scalar_one_or_none()

        if not structured_data:
            return None

        full_text = structured_data.get("full_text", "")
        if not full_text:
            return None

        content = full_text[entry.char_start:entry.char_end]
        section = SectionContent(
            paper_id=toc.paper_id,
            section_title=entry.title,
            content=content.strip(),
            word_count=len(content.split()),
            has_subsections=len(entry.children) > 0,
        )

        # Store in cache
        if self._redis:
            try:
                await self._redis.client.setex(
                    cache_key, _SECTION_CACHE_TTL, json.dumps(section.model_dump())
                )
            except Exception:
                logger.debug("Failed to cache section %s", cache_key)

        return section

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
