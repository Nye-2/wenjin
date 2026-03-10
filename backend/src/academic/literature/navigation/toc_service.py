# src/academic/literature/navigation/toc_service.py
"""TOC navigation service."""

import re
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, PaperExtraction
from .models import PaperTOC, TOCEntry

logger = logging.getLogger(__name__)


class TocService:
    """Service for TOC-based paper navigation.

    This service extracts and manages Table of Contents (TOC) for papers,
    enabling hierarchical navigation through paper sections.
    """

    # Common section title patterns for markdown headers
    SECTION_PATTERNS = [
        r"^#\s+(\d+\.?\s*.+)$",           # "# 1. Introduction"
        r"^##\s+(\d+\.\d+\s*.+)$",        # "## 1.1 Background"
        r"^###\s+(\d+\.\d+\.\d+\s*.+)$",  # "### 1.1.1 Details"
        r"^#+\s*(Abstract|Introduction|Methods?|Results?|Discussion|Conclusion|References|Acknowledgements?)\s*$",
    ]

    def __init__(self, db: AsyncSession):
        """Initialize TocService.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def get_paper_toc(self, paper_id: str) -> PaperTOC | None:
        """Get TOC structure for a paper.

        Retrieves the paper and its extraction data to build a hierarchical TOC.

        Args:
            paper_id: Paper ID

        Returns:
            PaperTOC if found, None otherwise
        """
        # Get paper
        paper_result = await self.db.execute(
            select(Paper).where(Paper.id == paper_id)
        )
        paper = paper_result.scalar_one_or_none()

        if not paper:
            return None

        # Get extraction with full_text
        extraction_result = await self.db.execute(
            select(PaperExtraction)
            .where(PaperExtraction.paper_id == paper_id)
            .where(PaperExtraction.extraction_type == "full_text")
            .order_by(PaperExtraction.tier.desc(), PaperExtraction.created_at.desc())
            .limit(1)
        )
        extraction = extraction_result.scalar_one_or_none()

        # Get full_text from extraction or use empty string
        full_text = ""
        if extraction and extraction.structured_data:
            full_text = extraction.structured_data.get("full_text", "")

        # Extract TOC from full_text
        entries = self._extract_toc_entries(full_text)

        return PaperTOC(
            paper_id=paper.id,
            title=paper.title,
            abstract=paper.abstract or "",
            entries=entries,
            total_chars=len(full_text),
        )

    def _extract_toc_entries(self, text: str) -> list[TOCEntry]:
        """Extract TOC entries from paper text.

        Parses markdown headers to identify sections and their hierarchy.

        Args:
            text: Full paper text (markdown format)

        Returns:
            List of TOCEntry objects with hierarchical structure
        """
        entries = []
        lines = text.split("\n")

        # Track character positions
        char_pos = 0
        section_positions = []

        for line in lines:
            for pattern in self.SECTION_PATTERNS:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    level = line.count("#")
                    title = match.group(1) if match.lastindex else line.lstrip("#").strip()
                    section_positions.append({
                        "title": title,
                        "level": level,
                        "char_start": char_pos,
                    })
                    break
            char_pos += len(line) + 1  # +1 for newline

        # Build flat entries with char_end
        for i, pos in enumerate(section_positions):
            next_char = section_positions[i + 1]["char_start"] if i + 1 < len(section_positions) else len(text)
            entries.append(TOCEntry(
                title=pos["title"],
                level=pos["level"],
                char_start=pos["char_start"],
                char_end=next_char,
                children=[],
            ))

        # Build hierarchy (level 1 contains level 2, etc.)
        return self._build_hierarchy(entries)

    def _build_hierarchy(self, entries: list[TOCEntry]) -> list[TOCEntry]:
        """Build hierarchical structure from flat entries.

        Organizes sections into a tree structure where level N+1 sections
        become children of the nearest preceding level N section.

        Args:
            entries: Flat list of TOCEntry objects

        Returns:
            List of top-level TOCEntry objects with nested children
        """
        if not entries:
            return []

        root_entries = []
        stack = []  # Stack of (level, entry)

        for entry in entries:
            # Pop entries with >= current level
            while stack and stack[-1][0] >= entry.level:
                stack.pop()

            if stack:
                # Add as child of top of stack
                stack[-1][1].children.append(entry)
            else:
                # Top-level entry
                root_entries.append(entry)

            stack.append((entry.level, entry))

        return root_entries
