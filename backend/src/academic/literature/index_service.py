"""Index-based literature navigation service.

This module provides index-based (TOC-driven) navigation through literature,
as an alternative to vector-based RAG retrieval. It allows agents to browse
papers by their table of contents and retrieve specific sections.
"""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, PaperExtraction, WorkspacePaper


class IndexService:
    """Service for index-based literature navigation.

    This service provides TOC-based navigation through literature:
    - Get workspace TOC summary: formatted list of all paper TOCs
    - Get paper TOC: list of sections/chapters
    - Get paper section: retrieve specific section content

    This is useful for agents that need to understand paper structure
    before deciding what to read, without using vector embeddings.
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def get_workspace_toc_summary(self, workspace_id: str) -> str:
        """Get formatted TOC summary for all papers in a workspace.

        This returns a formatted string listing all papers and their
        table of contents, suitable for injection into agent context.

        Args:
            workspace_id: Workspace ID to get papers for

        Returns:
            Formatted string with TOC overview, or empty string if no papers

        Example output:
            ## 文献库概览

            ### [1] Attention Is All You Need (2017)
            - 目录: 1. Introduction, 2. Background, 3. Model Architecture, 4. Experiments

            ### [2] BERT (2019)
            - 目录: 1. Introduction, 2. Related Work, 3. BERT, 4. Experiments
        """
        # Get all papers in workspace
        query = (
            select(Paper)
            .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
            .where(WorkspacePaper.workspace_id == workspace_id)
            .order_by(WorkspacePaper.created_at.desc())
        )
        result = await self.db.execute(query)
        papers = list(result.scalars().all())

        if not papers:
            return ""

        # Build formatted TOC summary
        lines = ["## 文献库概览"]

        for idx, paper in enumerate(papers, 1):
            year_str = f" ({paper.year})" if paper.year else ""
            lines.append("")
            lines.append(f"### [{idx}] {paper.title}{year_str}")

            # Get TOC for this paper
            toc_items = await self.get_paper_toc(paper.id)

            if toc_items:
                toc_str = ", ".join(
                    f"{item.get('number', '')}. {item.get('title', '')}"
                    for item in toc_items
                )
                lines.append(f"- 目录: {toc_str}")
            else:
                lines.append("- 目录: (暂无目录信息)")

        return "\n".join(lines)

    async def get_paper_toc(self, paper_id: str) -> list[dict]:
        """Get table of contents for a specific paper.

        Retrieves the TOC from the paper's extraction data (tier 2 LLM extraction).

        Args:
            paper_id: Paper ID to get TOC for

        Returns:
            List of TOC items, each with 'number' and 'title' keys.
            Returns empty list if no TOC is available.

        Example:
            [
                {"number": "1", "title": "Introduction"},
                {"number": "2", "title": "Background"},
                {"number": "3", "title": "Model Architecture"},
            ]
        """
        # Get latest tier 2 extraction (LLM extraction has better TOC)
        query = (
            select(PaperExtraction)
            .where(PaperExtraction.paper_id == paper_id)
            .where(PaperExtraction.extraction_type == "full_text")
            .order_by(PaperExtraction.tier.desc(), PaperExtraction.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        extraction = result.scalar_one_or_none()

        if not extraction or not extraction.structured_data:
            return []

        toc = extraction.structured_data.get("toc", [])
        return toc if isinstance(toc, list) else []

    async def get_paper_section(
        self,
        paper_id: str,
        section_path: str,
    ) -> dict | None:
        """Get content of a specific section from a paper.

        Retrieves section content from the paper's extraction data.

        Args:
            paper_id: Paper ID to get section from
            section_path: Section identifier (e.g., "1", "2.1", "3.2.1")

        Returns:
            Dictionary with section 'title' and 'content', or None if not found.

        Example:
            {
                "title": "Introduction",
                "content": "In recent years, deep learning has..."
            }
        """
        # Get latest extraction with section data
        query = (
            select(PaperExtraction)
            .where(PaperExtraction.paper_id == paper_id)
            .where(PaperExtraction.extraction_type == "full_text")
            .order_by(PaperExtraction.tier.desc(), PaperExtraction.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        extraction = result.scalar_one_or_none()

        if not extraction or not extraction.structured_data:
            return None

        sections = extraction.structured_data.get("sections", {})
        if not sections:
            return None

        # Look up section by path
        section = sections.get(section_path)
        if not section:
            return None

        return {
            "title": section.get("title", ""),
            "content": section.get("content", ""),
        }
