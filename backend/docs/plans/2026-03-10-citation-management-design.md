# Citation 引用管理系统设计文档

> **创建日期**: 2026-03-10
> **状态**: 已批准
> **作者**: Claude + 用户

## 1. 概述

### 1.1 背景

AcademiaGPT v2 完成了文献导航和工作区/论文服务优化后，需要完善引用管理功能：
- `src/academic/citation/` 目录为空
- 缺少引用格式化功能（APA/MLA/Chicago/IEEE）
- 无法导入/导出 BibTeX
- 无 LLM 可调用的引用管理工具
- 缺少引用关系存储和图谱

### 1.2 目标

构建完整的引用管理系统：
- 多格式引用格式化（APA/MLA/Chicago/IEEE）
- BibTeX 导入/导出
- 引用关系存储和查询
- LLM 工具集成

### 1.3 范围

**包含：**
- Citation 数据模型
- 引用格式化服务
- BibTeX 解析器和导出器
- 6 个 LLM 工具

**不包含：**
- 引用关系可视化（后续 Phase）
- PDF 自动提取引用（后续 Phase）

## 2. 数据模型

### 2.1 Citation 模型

```python
# src/database/models/citation.py

class CitationType(enum.StrEnum):
    """Types of citations."""
    EXPLICIT = "explicit"      # Direct citation with reference
    IMPLICIT = "implicit"      # Mentioned without formal reference
    SELF = "self"              # Self-citation
    SECONDARY = "secondary"    # Cited by another source


class Citation(Base, UUIDMixin, TimestampMixin):
    """Citation relationship between papers.

    Represents a citation from one paper to another,
    with context and metadata about where the citation appears.
    """

    __tablename__ = "citations"
    __table_args__ = (
        Index("ix_citations_source", "paper_id"),
        Index("ix_citations_target", "cited_paper_id"),
        Index("ix_citations_workspace", "workspace_id"),
        UniqueConstraint("paper_id", "cited_paper_id", "workspace_id",
                        name="uq_citation_relationship"),
    )

    # Source paper (the one that cites)
    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Target paper (the one being cited)
    cited_paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Workspace context
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Citation details
    citation_type: Mapped[str] = mapped_column(
        String(20),
        default=CitationType.EXPLICIT,
        nullable=False,
    )

    # Context information
    citation_context: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )  # Text surrounding the citation

    section: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )  # Section where citation appears

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )  # Page number in source paper

    # Relationships
    paper: Mapped["Paper"] = relationship(
        "Paper",
        foreign_keys=[paper_id],
        back_populates="outgoing_citations",
    )
    cited_paper: Mapped["Paper"] = relationship(
        "Paper",
        foreign_keys=[cited_paper_id],
        back_populates="incoming_citations",
    )
    workspace: Mapped["Workspace"] = relationship("Workspace")
```

### 2.2 Paper 模型扩展

```python
# Add to src/database/models/paper.py

class Paper(Base, UUIDMixin, TimestampMixin):
    # ... existing fields ...

    # New relationships for citations
    outgoing_citations: Mapped[list["Citation"]] = relationship(
        "Citation",
        foreign_keys="Citation.paper_id",
        back_populates="paper",
        cascade="all, delete-orphan",
    )
    incoming_citations: Mapped[list["Citation"]] = relationship(
        "Citation",
        foreign_keys="Citation.cited_paper_id",
        back_populates="cited_paper",
        cascade="all, delete-orphan",
    )
```

## 3. 引用格式化服务

### 3.1 格式化器基类

```python
# src/academic/citation/formatters/base.py

from abc import ABC, abstractmethod
from typing import Any


class CitationFormatter(ABC):
    """Base class for citation formatters."""

    @property
    @abstractmethod
    def style_name(self) -> str:
        """Return the style name (e.g., 'APA', 'MLA')."""
        pass

    @abstractmethod
    def format_citation(self, paper: dict, in_text: bool = False) -> str:
        """Format a single citation.

        Args:
            paper: Paper metadata dict
            in_text: If True, format for in-text citation

        Returns:
            Formatted citation string
        """
        pass

    @abstractmethod
    def format_bibliography_entry(self, paper: dict) -> str:
        """Format a bibliography/reference list entry.

        Args:
            paper: Paper metadata dict

        Returns:
            Formatted bibliography entry
        """
        pass

    def format_authors(self, authors: list[dict]) -> str:
        """Format author list.

        Args:
            authors: List of author dicts with 'name' and optionally 'affiliation'

        Returns:
            Formatted author string
        """
        pass
```

### 3.2 APA 格式化器

```python
# src/academic/citation/formatters/apa.py

class APAFormatter(CitationFormatter):
    """APA 7th Edition citation formatter."""

    @property
    def style_name(self) -> str:
        return "APA"

    def format_authors(self, authors: list[dict]) -> str:
        """APA author format: Smith, J. A., & Jones, B. C."""
        if not authors:
            return ""

        formatted = []
        for author in authors:
            name = author.get("name", "")
            parts = name.split()
            if len(parts) >= 2:
                last = parts[-1]
                initials = ". ".join(p[0].upper() for p in parts[:-1]) + "."
                formatted.append(f"{last}, {initials}")
            else:
                formatted.append(name)

        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]} & {formatted[1]}"
        else:
            return ", ".join(formatted[:-1]) + ", & " + formatted[-1]

    def format_citation(self, paper: dict, in_text: bool = False) -> str:
        """Format APA citation.

        In-text: (Smith, 2024) or Smith (2024)
        Reference: Smith, J. A. (2024). Title. Journal, vol, pages.
        """
        authors = paper.get("authors", [])
        year = paper.get("year", "n.d.")

        if in_text:
            first_author = self._get_first_author_lastname(authors)
            if len(authors) > 1:
                return f"({first_author} et al., {year})"
            return f"({first_author}, {year})"

        return self.format_bibliography_entry(paper)

    def format_bibliography_entry(self, paper: dict) -> str:
        """Format APA bibliography entry."""
        parts = []

        # Authors
        authors = paper.get("authors", [])
        parts.append(self.format_authors(authors))

        # Year
        year = paper.get("year", "n.d.")
        parts.append(f"({year})")

        # Title
        title = paper.get("title", "")
        parts.append(f"{title}.")

        # Journal/Venue
        venue = paper.get("venue")
        if venue:
            parts.append(f"*{venue}*")

        # DOI
        doi = paper.get("doi")
        if doi:
            parts.append(f"https://doi.org/{doi}")

        return " ".join(parts)

    def _get_first_author_lastname(self, authors: list[dict]) -> str:
        if not authors:
            return "Unknown"
        name = authors[0].get("name", "")
        return name.split()[-1] if name else "Unknown"
```

### 3.3 其他格式化器

类似的模式实现：
- `MLAFormatter` - MLA 9th Edition
- `ChicagoFormatter` - Chicago 17th Edition
- `IEEEFormatter` - IEEE Citation Style

## 4. BibTeX 服务

### 4.1 BibTeX 解析器

```python
# src/academic/citation/bibtex/parser.py

import re
from typing import Iterator


class BibTeXParser:
    """Parse BibTeX files into structured data."""

    ENTRY_PATTERN = re.compile(
        r'@(\w+)\s*\{\s*([^,]+)\s*,',
        re.MULTILINE
    )

    FIELD_PATTERN = re.compile(
        r'(\w+)\s*=\s*[{\"]([^}\"]+)[}\"]',
        re.MULTILINE
    )

    def parse(self, content: str) -> list[dict]:
        """Parse BibTeX content into list of entries.

        Args:
            content: BibTeX file content

        Returns:
            List of entry dicts with 'type', 'key', and fields
        """
        entries = []

        for match in self.ENTRY_PATTERN.finditer(content):
            entry_type = match.group(1).lower()
            entry_key = match.group(2).strip()

            # Find entry body
            start = match.end()
            brace_count = 1
            end = start
            while end < len(content) and brace_count > 0:
                if content[end] == '{':
                    brace_count += 1
                elif content[end] == '}':
                    brace_count -= 1
                end += 1

            body = content[start:end-1]

            # Parse fields
            fields = {'type': entry_type, 'key': entry_key}
            for field_match in self.FIELD_PATTERN.finditer(body):
                field_name = field_match.group(1).lower()
                field_value = field_match.group(2).strip()
                fields[field_name] = field_value

            entries.append(fields)

        return entries

    def to_paper_dict(self, bibtex_entry: dict) -> dict:
        """Convert BibTeX entry to Paper-compatible dict.

        Args:
            bibtex_entry: Parsed BibTeX entry

        Returns:
            Paper-compatible dict
        """
        # Map BibTeX fields to Paper fields
        return {
            'title': bibtex_entry.get('title', ''),
            'authors': self._parse_authors(bibtex_entry.get('author', '')),
            'year': self._parse_year(bibtex_entry.get('year')),
            'venue': bibtex_entry.get('journal') or bibtex_entry.get('booktitle', ''),
            'doi': bibtex_entry.get('doi'),
            'source': 'bibtex_import',
        }

    def _parse_authors(self, author_str: str) -> list[dict]:
        """Parse BibTeX author string to list of dicts."""
        authors = []
        for name in author_str.split(' and '):
            name = name.strip()
            if name:
                authors.append({'name': name})
        return authors

    def _parse_year(self, year_str: str | None) -> int | None:
        """Parse year string to int."""
        if not year_str:
            return None
        try:
            return int(year_str)
        except ValueError:
            return None
```

### 4.2 BibTeX 导出器

```python
# src/academic/citation/bibtex/exporter.py

class BibTeXExporter:
    """Export papers to BibTeX format."""

    ENTRY_TYPES = {
        'article': 'article',
        'inproceedings': 'inproceedings',
        'book': 'book',
        'phdthesis': 'phdthesis',
        'mastersthesis': 'mastersthesis',
        'misc': 'misc',
    }

    def export(self, papers: list[dict]) -> str:
        """Export papers to BibTeX format.

        Args:
            papers: List of paper dicts

        Returns:
            BibTeX formatted string
        """
        entries = []

        for paper in papers:
            entry = self._format_entry(paper)
            entries.append(entry)

        return '\n\n'.join(entries)

    def _format_entry(self, paper: dict) -> str:
        """Format single paper as BibTeX entry."""
        entry_type = self._determine_type(paper)
        key = self._generate_key(paper)

        lines = [f"@{entry_type}{{{key},"]

        # Required fields
        if paper.get('authors'):
            authors = ' and '.join(
                a.get('name', '') for a in paper['authors']
            )
            lines.append(f"  author = {{{authors}}},")

        if paper.get('title'):
            lines.append(f"  title = {{{paper['title']}}},")

        # Optional fields
        if paper.get('year'):
            lines.append(f"  year = {{{paper['year']}}},")

        if paper.get('venue'):
            if entry_type == 'article':
                lines.append(f"  journal = {{{paper['venue']}}},")
            elif entry_type == 'inproceedings':
                lines.append(f"  booktitle = {{{paper['venue']}}},")

        if paper.get('doi'):
            lines.append(f"  doi = {{{paper['doi']}}},")

        if paper.get('abstract'):
            lines.append(f"  abstract = {{{paper['abstract']}}},")

        lines.append("}")

        return '\n'.join(lines)

    def _determine_type(self, paper: dict) -> str:
        """Determine BibTeX entry type from paper metadata."""
        # Simple heuristic based on venue
        venue = (paper.get('venue') or '').lower()
        if 'conference' in venue or 'workshop' in venue:
            return 'inproceedings'
        elif 'journal' in venue or 'transactions' in venue:
            return 'article'
        return 'misc'

    def _generate_key(self, paper: dict) -> str:
        """Generate BibTeX citation key."""
        parts = []

        # First author lastname
        authors = paper.get('authors', [])
        if authors:
            name = authors[0].get('name', '')
            parts.append(name.split()[-1].lower())

        # Year
        if paper.get('year'):
            parts.append(str(paper['year']))

        # First word of title
        title = paper.get('title', '')
        if title:
            first_word = ''.join(c for c in title.split()[0] if c.isalnum())
            parts.append(first_word.lower())

        return '_'.join(parts) if parts else 'unknown'
```

## 5. LLM 工具

### 5.1 工具列表

```python
# src/academic/citation/tools.py

from langchain_core.tools import tool, InjectedToolArg
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal


@tool
async def format_citation(
    paper_id: str,
    style: Literal["apa", "mla", "chicago", "ieee"] = "apa",
    in_text: bool = False,
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Format a paper citation in specified style.

    Args:
        paper_id: Paper ID to format
        style: Citation style (apa, mla, chicago, ieee)
        in_text: Return in-text citation format if True

    Returns:
        Formatted citation string
    """
    pass


@tool
async def format_bibliography(
    workspace_id: str,
    style: Literal["apa", "mla", "chicago", "ieee"] = "apa",
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Format bibliography for all papers in workspace.

    Args:
        workspace_id: Workspace ID
        style: Citation style (apa, mla, chicago, ieee)

    Returns:
        Formatted bibliography as markdown string
    """
    pass


@tool
async def export_bibtex(
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Export workspace papers as BibTeX.

    Args:
        workspace_id: Workspace ID

    Returns:
        BibTeX formatted string
    """
    pass


@tool
async def import_bibtex(
    bibtex_content: str,
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
) -> str:
    """Import papers from BibTeX content.

    Args:
        bibtex_content: BibTeX formatted content
        workspace_id: Target workspace ID

    Returns:
        Import status with count of imported papers
    """
    pass


@tool
async def get_citation_graph(
    paper_id: str,
    depth: int = 1,
    db: AsyncSession = InjectedToolArg,
) -> dict:
    """Get citation graph for a paper.

    Args:
        paper_id: Paper ID to analyze
        depth: How many levels of citations to include

    Returns:
        Citation graph with nodes and edges
    """
    pass


@tool
async def add_citation(
    paper_id: str,
    cited_paper_id: str,
    workspace_id: str,
    db: AsyncSession = InjectedToolArg,
    citation_context: str | None = None,
    section: str | None = None,
) -> str:
    """Add citation relationship between papers.

    Args:
        paper_id: Source paper (the one that cites)
        cited_paper_id: Target paper (the one being cited)
        workspace_id: Workspace context
        citation_context: Text surrounding the citation (optional)
        section: Section where citation appears (optional)

    Returns:
        Status message
    """
    pass
```

## 6. 服务层

### 6.1 CitationService

```python
# src/academic/citation/service.py

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, Citation


class CitationService:
    """Service for managing citations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_citation(
        self,
        paper_id: str,
        cited_paper_id: str,
        workspace_id: str,
        citation_context: str | None = None,
        section: str | None = None,
    ) -> Citation:
        """Add citation relationship."""
        pass

    async def get_outgoing_citations(
        self,
        paper_id: str,
        workspace_id: str,
    ) -> list[Citation]:
        """Get papers cited by this paper."""
        pass

    async def get_incoming_citations(
        self,
        paper_id: str,
        workspace_id: str,
    ) -> list[Citation]:
        """Get papers that cite this paper."""
        pass

    async def get_citation_graph(
        self,
        paper_id: str,
        workspace_id: str,
        depth: int = 1,
    ) -> dict:
        """Get citation graph with specified depth."""
        pass

    async def remove_citation(
        self,
        paper_id: str,
        cited_paper_id: str,
        workspace_id: str,
    ) -> bool:
        """Remove citation relationship."""
        pass
```

## 7. 目录结构

```
src/
├── academic/
│   └── citation/
│       ├── __init__.py
│       ├── service.py           # CitationService
│       ├── tools.py             # LLM tools
│       ├── formatters/
│       │   ├── __init__.py
│       │   ├── base.py          # Base formatter
│       │   ├── apa.py           # APA style
│       │   ├── mla.py           # MLA style
│       │   ├── chicago.py       # Chicago style
│       │   └── ieee.py          # IEEE style
│       └── bibtex/
│           ├── __init__.py
│           ├── parser.py        # BibTeX parser
│           └── exporter.py      # BibTeX exporter
├── database/
│   └── models/
│       └── citation.py          # Citation model
└── agents/
    └── lead_agent/
        └── agent.py             # Register citation tools

tests/
└── academic/
    └── citation/
        ├── test_service.py
        ├── test_formatters.py
        ├── test_bibtex.py
        └── test_tools.py
```

## 8. 验收标准

### 8.1 数据模型
- [ ] Citation 模型已创建
- [ ] Paper 模型已扩展引用关系
- [ ] 数据库迁移已创建

### 8.2 引用格式化
- [ ] APA 格式化器已实现
- [ ] MLA 格式化器已实现
- [ ] Chicago 格式化器已实现
- [ ] IEEE 格式化器已实现

### 8.3 BibTeX 支持
- [ ] BibTeX 解析器已实现
- [ ] BibTeX 导出器已实现
- [ ] 支持常见 BibTeX 字段

### 8.4 LLM 工具
- [ ] format_citation 工具可用
- [ ] format_bibliography 工具可用
- [ ] export_bibtex 工具可用
- [ ] import_bibtex 工具可用
- [ ] get_citation_graph 工具可用
- [ ] add_citation 工具可用

### 8.5 测试
- [ ] 单元测试覆盖率 > 80%
- [ ] 所有测试通过

## 9. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| BibTeX 解析复杂 | 使用成熟库如 bibtexparser 或简化解析 |
| 引用格式变体多 | 参考官方样式指南，先实现核心格式 |
| 性能问题（大量引用） | 添加分页和索引优化 |
