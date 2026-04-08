"""Index-based literature navigation service.

This module provides index-based (TOC-driven) navigation through literature,
as an alternative to vector-based RAG retrieval. It allows agents to browse
papers by their table of contents and retrieve specific sections.
"""


from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, PaperExtraction, PaperSection, WorkspacePaper


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
                    (
                        f"{str(item.get('number') or '').strip()}. {item.get('title', '')}"
                        if str(item.get("number") or "").strip()
                        else str(item.get("title") or "")
                    )
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
        normalized = self._normalize_toc_entries(toc)
        if normalized:
            return normalized

        return await self._load_toc_from_sections(paper_id)

    async def get_paper_section(
        self,
        paper_id: str,
        section_path: str,
        workspace_id: str | None = None,
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
        # First try canonical section store
        section = await self._load_section_from_store(
            paper_id=paper_id,
            section_key=section_path,
            workspace_id=workspace_id,
        )
        if section is not None:
            return section

        # Fallback: extraction JSON payload
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

    async def get_paper_section_by_title(
        self,
        paper_id: str,
        section_title: str,
        workspace_id: str | None = None,
    ) -> dict | None:
        """Get content of a section by title from canonical store."""
        normalized_title = str(section_title or "").strip()
        if not normalized_title:
            return None
        return await self._load_section_from_store(
            paper_id=paper_id,
            section_key=normalized_title,
            workspace_id=workspace_id,
            by_title=True,
        )

    async def search_workspace_sections(
        self,
        workspace_id: str,
        query: str,
        *,
        limit: int = 8,
    ) -> list[dict[str, str | int]]:
        """Search section titles/content inside one workspace."""
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []

        escaped_query = normalized_query.replace("%", "\\%").replace("_", "\\_")
        stmt = (
            select(PaperSection, Paper)
            .join(Paper, Paper.id == PaperSection.paper_id)
            .where(PaperSection.workspace_id == workspace_id)
            .where(
                or_(
                    PaperSection.section_title.ilike(
                        f"%{escaped_query}%",
                        escape="\\",
                    ),
                    PaperSection.content.ilike(f"%{escaped_query}%", escape="\\"),
                    Paper.title.ilike(f"%{escaped_query}%", escape="\\"),
                )
            )
            .order_by(PaperSection.updated_at.desc())
            .limit(max(1, min(limit, 50)))
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        records: list[dict[str, str | int]] = []
        lowered_query = normalized_query.lower()
        for section, paper in rows:
            content = str(section.content or "")
            snippet = content[:320]
            if lowered_query and content:
                idx = content.lower().find(lowered_query)
                if idx >= 0:
                    start = max(0, idx - 120)
                    end = min(len(content), idx + max(len(normalized_query), 1) + 160)
                    snippet = content[start:end]
            records.append(
                {
                    "paper_id": str(section.paper_id),
                    "paper_title": str(paper.title or ""),
                    "section_path": str(section.section_path or ""),
                    "section_title": str(section.section_title or ""),
                    "level": int(section.level or 1),
                    "page_start": int(section.page_start or 1),
                    "page_end": int(section.page_end or 1),
                    "snippet": snippet,
                }
            )

        return records

    async def _load_toc_from_sections(self, paper_id: str) -> list[dict]:
        result = await self.db.execute(
            select(PaperSection)
            .where(PaperSection.paper_id == paper_id)
            .order_by(PaperSection.section_path)
        )
        sections = result.scalars().all()
        if not sections:
            return []

        toc_items: list[dict] = []
        seen_paths: set[str] = set()
        for section in sections:
            path = str(section.section_path or "").strip()
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            toc_items.append(
                {
                    "number": path,
                    "title": str(section.section_title or "").strip(),
                    "level": int(section.level or 1),
                    "page": int(section.page_start or 1),
                }
            )
        return toc_items

    def _normalize_toc_entries(self, toc: object) -> list[dict]:
        if not isinstance(toc, list):
            return []

        items: list[dict] = []
        for idx, item in enumerate(toc, 1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            number = str(
                item.get("number")
                or item.get("section_path")
                or item.get("path")
                or idx
            ).strip()
            level_raw = item.get("level")
            try:
                level = int(level_raw) if level_raw is not None else 1
            except (TypeError, ValueError):
                level = 1
            page_raw = item.get("page")
            try:
                page = int(page_raw) if page_raw is not None else 1
            except (TypeError, ValueError):
                page = 1
            items.append(
                {
                    "number": number or str(idx),
                    "title": title,
                    "level": max(level, 1),
                    "page": max(page, 1),
                }
            )
        return items

    async def _load_section_from_store(
        self,
        *,
        paper_id: str,
        section_key: str,
        workspace_id: str | None = None,
        by_title: bool = False,
    ) -> dict | None:
        stmt = select(PaperSection).where(PaperSection.paper_id == paper_id)
        if workspace_id:
            stmt = stmt.where(PaperSection.workspace_id == workspace_id)
        if by_title:
            escaped_key = section_key.replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(
                PaperSection.section_title.ilike(f"%{escaped_key}%", escape="\\")
            )
        else:
            stmt = stmt.where(PaperSection.section_path == section_key)
        stmt = stmt.order_by(PaperSection.updated_at.desc()).limit(1)

        result = await self.db.execute(stmt)
        section = result.scalar_one_or_none()
        if section is None:
            return None

        return {
            "title": str(section.section_title or ""),
            "content": str(section.content or ""),
            "section_path": str(section.section_path or ""),
            "page_start": int(section.page_start or 1),
            "page_end": int(section.page_end or 1),
            "level": int(section.level or 1),
        }
