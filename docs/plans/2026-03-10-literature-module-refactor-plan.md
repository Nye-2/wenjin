# 文献管理模块精简重构 - 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将文献管理模块重构为 TOC-Driven 检索系统，移除 RAG 向量检索，集成外部学术数据库

**Architecture:** 基于论文目录结构的导航系统，LLM 通过工具主动调用获取章节内容，外部数据库统一抽象

**Tech Stack:** Python 3.12+, Pydantic, SQLAlchemy, httpx (外部 API 调用), LangChain Tools

---

## 前置准备

### 参考文件
- 设计文档: `docs/plans/2026-03-10-literature-module-refactor-design.md`
- 现有代码: `backend/src/academic/literature/`
- 数据模型: `backend/src/academic/database/models.py`

### 当前文件结构
```
src/academic/literature/
├── __init__.py
├── extraction/
│   ├── __init__.py
│   └── pdf_extractor.py
├── rag/                    # ← 待删除
│   ├── __init__.py
│   ├── rag_service.py
│   └── tools.py
├── sharing/
├── index_service.py
├── tools.py
└── tools.py.bak
```

---

## Task 1: 删除 RAG 模块

**Files:**
- Delete: `backend/src/academic/literature/rag/` (整个目录)
- Modify: `backend/src/academic/literature/__init__.py`
- Modify: `backend/src/academic/literature/tools.py`

**Step 1: 确认 RAG 模块位置和依赖**

Run: `cd /home/cjz/academiagpt-v2/backend && find . -name "*.py" -exec grep -l "from.*rag" {} \; | head -20`
Expected: 列出所有导入 RAG 模块的文件

**Step 2: 删除 RAG 目录**

Run: `rm -rf src/academic/literature/rag/`
Expected: 目录删除成功

**Step 3: 更新 literature/__init__.py**

```python
# src/academic/literature/__init__.py
"""Literature module initialization."""

from .extraction.pdf_extractor import PDFExtractor
from .navigation.models import PaperTOC, SectionContent, TOCEntry
from .navigation.toc_service import TocService
from .navigation.section_loader import SectionLoader

__all__ = [
    "PDFExtractor",
    "PaperTOC",
    "SectionContent",
    "TOCEntry",
    "TocService",
    "SectionLoader",
]
```

**Step 4: 更新 tools.py 移除 RAG 相关工具**

修改 `backend/src/academic/literature/tools.py`:
- 移除 `rag_retrieve_tool` 相关代码
- 保留其他工具

**Step 5: 提交**

```bash
git add -A
git commit -m "refactor(literature): remove RAG vector retrieval module

Breaking change: RAG vector retrieval removed, will be replaced
with TOC-driven navigation in following commits.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: 创建导航模块数据模型

**Files:**
- Create: `backend/src/academic/literature/navigation/__init__.py`
- Create: `backend/src/academic/literature/navigation/models.py`

**Step 1: 创建 navigation 目录**

Run: `mkdir -p src/academic/literature/navigation`

**Step 2: 创建 __init__.py**

```python
# src/academic/literature/navigation/__init__.py
"""TOC navigation module."""

from .models import PaperTOC, SectionContent, TOCEntry
from .toc_service import TocService
from .section_loader import SectionLoader

__all__ = ["PaperTOC", "SectionContent", "TOCEntry", "TocService", "SectionLoader"]
```

**Step 3: 创建 models.py**

```python
# src/academic/literature/navigation/models.py
"""Data models for TOC navigation."""

from pydantic import BaseModel, Field


class TOCEntry(BaseModel):
    """论文目录条目"""
    title: str = Field(..., description="章节标题")
    level: int = Field(..., ge=1, le=5, description="层级 (1=章, 2=节, 3=小节)")
    page_start: int | None = Field(None, description="起始页码")
    char_start: int = Field(..., ge=0, description="在全文中的字符起始位置")
    char_end: int = Field(..., ge=0, description="字符结束位置")
    children: list["TOCEntry"] = Field(default_factory=list, description="子章节")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "3. Methodology",
                "level": 1,
                "page_start": 5,
                "char_start": 15000,
                "char_end": 25000,
                "children": [
                    {
                        "title": "3.1 Dataset",
                        "level": 2,
                        "char_start": 16000,
                        "char_end": 18000,
                        "children": []
                    }
                ]
            }
        }


class PaperTOC(BaseModel):
    """论文完整目录结构"""
    paper_id: str = Field(..., description="论文 ID")
    title: str = Field(..., description="论文标题")
    abstract: str = Field(default="", description="摘要内容，始终可访问")
    entries: list[TOCEntry] = Field(default_factory=list, description="目录条目列表")
    total_chars: int = Field(default=0, ge=0, description="全文字符数")

    def find_entry(self, title: str) -> TOCEntry | None:
        """通过标题查找目录条目"""
        return self._find_entry_recursive(title, self.entries)

    def _find_entry_recursive(self, title: str, entries: list[TOCEntry]) -> TOCEntry | None:
        for entry in entries:
            if entry.title.lower() == title.lower():
                return entry
            if entry.children:
                found = self._find_entry_recursive(title, entry.children)
                if found:
                    return found
        return None


class SectionContent(BaseModel):
    """章节内容"""
    paper_id: str = Field(..., description="论文 ID")
    section_title: str = Field(..., description="章节标题")
    content: str = Field(..., description="章节 markdown 内容")
    word_count: int = Field(default=0, ge=0, description="字数统计")
    has_subsections: bool = Field(default=False, description="是否有子章节")

    class Config:
        json_schema_extra = {
            "example": {
                "paper_id": "paper-123",
                "section_title": "3. Methodology",
                "content": "## 3. Methodology\n\nWe propose a novel approach...",
                "word_count": 1500,
                "has_subsections": True
            }
        }
```

**Step 4: 提交**

```bash
git add src/academic/literature/navigation/
git commit -m "feat(literature): add TOC navigation data models

- Add TOCEntry for hierarchical table of contents
- Add PaperTOC for paper-wide TOC structure
- Add SectionContent for section content retrieval

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: 创建 TOC 服务

**Files:**
- Create: `backend/src/academic/literature/navigation/toc_service.py`
- Test: `backend/tests/unit/literature/test_toc_service.py`

**Step 1: 写测试文件**

```python
# tests/unit/literature/test_toc_service.py
"""Tests for TocService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.literature.navigation.models import PaperTOC, TOCEntry
from src.academic.literature.navigation.toc_service import TocService


@pytest.fixture
def mock_db():
    """Mock database session."""
    from unittest.mock import AsyncMock
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def toc_service(mock_db):
    """Create TocService instance."""
    return TocService(mock_db)


class TestTocService:
    """Tests for TocService."""

    @pytest.mark.asyncio
    async def test_get_paper_toc_returns_structure(self, toc_service, mock_db):
        """Test that get_paper_toc returns correct structure."""
        # Setup mock
        from unittest.mock import MagicMock
        mock_paper = MagicMock()
        mock_paper.id = "paper-123"
        mock_paper.title = "Test Paper"
        mock_paper.abstract = "This is an abstract"
        mock_paper.full_text = "# 1. Introduction\n\nContent here...\n\n# 2. Methods\n\nMore content..."

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_paper
        mock_db.execute.return_value = mock_result

        # Execute
        result = await toc_service.get_paper_toc("paper-123")

        # Assert
        assert result is not None
        assert result.paper_id == "paper-123"
        assert result.title == "Test Paper"

    @pytest.mark.asyncio
    async def test_get_paper_toc_returns_none_if_not_found(self, toc_service, mock_db):
        """Test that get_paper_toc returns None for non-existent paper."""
        from unittest.mock import MagicMock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await toc_service.get_paper_toc("nonexistent")

        assert result is None
```

**Step 2: 运行测试验证失败**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/literature/test_toc_service.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: 实现 TocService**

```python
# src/academic/literature/navigation/toc_service.py
"""TOC navigation service."""

import re
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.database.models import Paper
from .models import PaperTOC, TOCEntry

logger = logging.getLogger(__name__)


class TocService:
    """Service for TOC-based paper navigation."""

    # 常见章节标题模式
    SECTION_PATTERNS = [
        r"^#\s+(\d+\.?\s+.+)$",           # "1. Introduction", "# 1. Introduction"
        r"^##\s+(\d+\.\d+\s+.+)$",        # "1.1 Background"
        r"^###\s+(\d+\.\d+\.\d+\s+.+)$",  # "1.1.1 Details"
        r"^#+\s+(Abstract|Introduction|Methods?|Results?|Discussion|Conclusion|References|Acknowledgements?)\s*$",
    ]

    def __init__(self, db: AsyncSession):
        """Initialize TocService.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def get_paper_toc(self, paper_id: str) -> PaperTOC | None:
        """Get TOC structure for a paper.

        Args:
            paper_id: Paper ID

        Returns:
            PaperTOC if found, None otherwise
        """
        result = await self.db.execute(
            select(Paper).where(Paper.id == paper_id)
        )
        paper = result.scalar_one_or_none()

        if not paper:
            return None

        # Extract TOC from full_text
        full_text = paper.full_text or ""
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

        Args:
            text: Full paper text

        Returns:
            List of TOCEntry objects
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

        # Build hierarchical structure and set char_end
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
        """Build hierarchical structure from flat entries."""
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
```

**Step 4: 运行测试验证通过**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/literature/test_toc_service.py -v`
Expected: PASS

**Step 5: 提交**

```bash
git add src/academic/literature/navigation/toc_service.py tests/unit/literature/test_toc_service.py
git commit -m "feat(literature): add TocService for TOC extraction

- Extract hierarchical TOC from paper full_text
- Support common section patterns (# 1. Introduction, etc.)
- Build parent-child relationships between sections

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: 创建章节加载器

**Files:**
- Create: `backend/src/academic/literature/navigation/section_loader.py`
- Test: `backend/tests/unit/literature/test_section_loader.py`

**Step 1: 写测试文件**

```python
# tests/unit/literature/test_section_loader.py
"""Tests for SectionLoader."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.academic.literature.navigation.models import PaperTOC, TOCEntry
from src.academic.literature.navigation.section_loader import SectionLoader


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def section_loader(mock_db):
    """Create SectionLoader instance."""
    return SectionLoader(mock_db)


@pytest.fixture
def sample_toc():
    """Create sample TOC."""
    return PaperTOC(
        paper_id="paper-123",
        title="Test Paper",
        abstract="Abstract text",
        entries=[
            TOCEntry(
                title="1. Introduction",
                level=1,
                char_start=0,
                char_end=100,
                children=[],
            ),
            TOCEntry(
                title="2. Methods",
                level=1,
                char_start=100,
                char_end=300,
                children=[
                    TOCEntry(
                        title="2.1 Dataset",
                        level=2,
                        char_start=150,
                        char_end=200,
                        children=[],
                    ),
                ],
            ),
        ],
        total_chars=500,
    )


class TestSectionLoader:
    """Tests for SectionLoader."""

    @pytest.mark.asyncio
    async def test_load_section_returns_content(self, section_loader, mock_db, sample_toc):
        """Test loading a section returns correct content."""
        # Setup mock
        mock_paper = MagicMock()
        mock_paper.id = "paper-123"
        mock_paper.full_text = "0" * 100 + "1" * 100 + "2" * 100 + "3" * 200

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_paper
        mock_db.execute.return_value = mock_result

        # Execute
        result = await section_loader.load_section(sample_toc, "1. Introduction")

        # Assert
        assert result is not None
        assert result.section_title == "1. Introduction"

    @pytest.mark.asyncio
    async def test_load_section_returns_none_if_not_found(self, section_loader, sample_toc):
        """Test loading non-existent section returns None."""
        result = await section_loader.load_section(sample_toc, "99. Nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_abstract_always_available(self, section_loader, sample_toc):
        """Test that abstract is always available."""
        result = await section_loader.get_abstract(sample_toc)

        assert result is not None
        assert result.section_title == "Abstract"
```

**Step 2: 运行测试验证失败**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/literature/test_section_loader.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: 实现 SectionLoader**

```python
# src/academic/literature/navigation/section_loader.py
"""Section content loader."""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.database.models import Paper
from .models import PaperTOC, SectionContent, TOCEntry

logger = logging.getLogger(__name__)


class SectionLoader:
    """Loader for paper section content."""

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

        # Get paper full text
        result = await self.db.execute(
            select(Paper.full_text).where(Paper.id == toc.paper_id)
        )
        full_text = result.scalar_one_or_none()

        if not full_text:
            logger.warning(f"Paper text not found: {toc.paper_id}")
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
```

**Step 4: 运行测试验证通过**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/literature/test_section_loader.py -v`
Expected: PASS

**Step 5: 提交**

```bash
git add src/academic/literature/navigation/section_loader.py tests/unit/literature/test_section_loader.py
git commit -m "feat(literature): add SectionLoader for content retrieval

- Load section content by title from paper full_text
- Abstract always available without DB query
- Support hierarchical section finding

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: 创建外部数据库基类

**Files:**
- Create: `backend/src/academic/literature/external/__init__.py`
- Create: `backend/src/academic/literature/external/base.py`
- Test: `backend/tests/unit/literature/external/test_base.py`

**Step 1: 创建 external 目录**

Run: `mkdir -p src/academic/literature/external`

**Step 2: 创建 __init__.py**

```python
# src/academic/literature/external/__init__.py
"""External academic database integration."""

from .base import ExternalDBBase, PaperSearchResult

__all__ = ["ExternalDBBase", "PaperSearchResult"]
```

**Step 3: 创建 base.py**

```python
# src/academic/literature/external/base.py
"""Base class for external academic databases."""

from abc import ABC, abstractmethod
from typing import Any, Literal
from pydantic import BaseModel, Field


class PaperSearchResult(BaseModel):
    """Unified search result from external databases."""

    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(default_factory=list, description="Author names")
    year: int | None = Field(None, description="Publication year")
    doi: str | None = Field(None, description="Digital Object Identifier")
    url: str | None = Field(None, description="Paper URL")
    abstract: str = Field(default="", description="Paper abstract")
    source: Literal["semantic_scholar", "arxiv", "crossref", "openalex"] = Field(
        ..., description="Source database"
    )
    citations_count: int | None = Field(None, description="Number of citations")
    venue: str | None = Field(None, description="Publication venue (journal/conference)")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Attention Is All You Need",
                "authors": ["Ashish Vaswani", "et al."],
                "year": 2017,
                "doi": "10.48550/arXiv.1706.03762",
                "url": "https://arxiv.org/abs/1706.03762",
                "abstract": "The dominant sequence transduction models...",
                "source": "arxiv",
                "citations_count": 50000,
                "venue": "NeurIPS 2017",
            }
        }


class ExternalDBBase(ABC):
    """Abstract base class for external academic databases."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Database name identifier."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable database name."""
        pass

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search for papers.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of PaperSearchResult objects
        """
        pass

    @abstractmethod
    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI.

        Args:
            doi: Digital Object Identifier

        Returns:
            PaperSearchResult if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """Get papers that cite this paper.

        Args:
            paper_id: Paper identifier in this database
            limit: Maximum number of citations to return

        Returns:
            List of citing papers
        """
        pass

    def _normalize_authors(self, authors: Any) -> list[str]:
        """Normalize author list to list of strings.

        Args:
            authors: Author data (various formats)

        Returns:
            List of author name strings
        """
        if not authors:
            return []
        if isinstance(authors, list):
            return [str(a) if isinstance(a, str) else a.get("name", str(a)) for a in authors]
        return [str(authors)]
```

**Step 4: 创建基础测试**

```python
# tests/unit/literature/external/test_base.py
"""Tests for external database base classes."""

import pytest
from src.academic.literature.external.base import PaperSearchResult


class TestPaperSearchResult:
    """Tests for PaperSearchResult model."""

    def test_create_search_result(self):
        """Test creating a search result."""
        result = PaperSearchResult(
            title="Test Paper",
            authors=["Author One", "Author Two"],
            year=2024,
            doi="10.1234/test",
            url="https://example.com/paper",
            abstract="An abstract",
            source="semantic_scholar",
        )

        assert result.title == "Test Paper"
        assert len(result.authors) == 2
        assert result.year == 2024

    def test_optional_fields(self):
        """Test that optional fields can be omitted."""
        result = PaperSearchResult(
            title="Minimal Paper",
            source="arxiv",
        )

        assert result.authors == []
        assert result.year is None
        assert result.doi is None
```

**Step 5: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/literature/external/test_base.py -v`
Expected: PASS

**Step 6: 提交**

```bash
git add src/academic/literature/external/ tests/unit/literature/external/
git commit -m "feat(literature): add external database base classes

- Add ExternalDBBase abstract class for DB integration
- Add PaperSearchResult unified result model
- Support extensible database integration pattern

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: 实现 Semantic Scholar 客户端

**Files:**
- Create: `backend/src/academic/literature/external/semantic_scholar.py`
- Test: `backend/tests/unit/literature/external/test_semantic_scholar.py`

**Step 1: 写测试**

```python
# tests/unit/literature/external/test_semantic_scholar.py
"""Tests for Semantic Scholar client."""

import pytest
from unittest.mock import AsyncMock, patch

from src.academic.literature.external.semantic_scholar import SemanticScholarClient


@pytest.fixture
def client():
    """Create client instance."""
    return SemanticScholarClient()


class TestSemanticScholarClient:
    """Tests for SemanticScholarClient."""

    def test_name_properties(self, client):
        """Test client name properties."""
        assert client.name == "semantic_scholar"
        assert client.display_name == "Semantic Scholar"

    @pytest.mark.asyncio
    async def test_search_returns_results(self, client):
        """Test search returns formatted results."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json.return_value = {
                "data": [
                    {
                        "paperId": "abc123",
                        "title": "Test Paper",
                        "authors": [{"name": "Author One"}],
                        "year": 2024,
                        "doi": "10.1234/test",
                        "url": "https://example.com",
                        "abstract": "Abstract text",
                        "citationCount": 100,
                        "venue": "ICML",
                    }
                ]
            }
            mock_response.raise_for_status = lambda: None
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            results = await client.search("machine learning", limit=5)

            assert len(results) == 1
            assert results[0].title == "Test Paper"
            assert results[0].source == "semantic_scholar"
```

**Step 2: 实现 SemanticScholarClient**

```python
# src/academic/literature/external/semantic_scholar.py
"""Semantic Scholar API client."""

import logging
from typing import Any

import httpx

from .base import ExternalDBBase, PaperSearchResult

logger = logging.getLogger(__name__)

# Semantic Scholar API base URL
API_BASE = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarClient(ExternalDBBase):
    """Client for Semantic Scholar API."""

    @property
    def name(self) -> str:
        return "semantic_scholar"

    @property
    def display_name(self) -> str:
        return "Semantic Scholar"

    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search Semantic Scholar for papers.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of search results
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/paper/search",
                params={
                    "query": query,
                    "limit": limit,
                    "fields": "paperId,title,authors,year,doi,url,abstract,citationCount,venue",
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("data", []):
            results.append(
                PaperSearchResult(
                    title=item.get("title", ""),
                    authors=self._normalize_authors(item.get("authors", [])),
                    year=item.get("year"),
                    doi=item.get("doi"),
                    url=item.get("url"),
                    abstract=item.get("abstract", ""),
                    source="semantic_scholar",
                    citations_count=item.get("citationCount"),
                    venue=item.get("venue"),
                )
            )

        return results

    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI.

        Args:
            doi: Paper DOI

        Returns:
            Paper if found, None otherwise
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/paper/DOI:{doi}",
                params={
                    "fields": "paperId,title,authors,year,doi,url,abstract,citationCount,venue",
                },
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            item = response.json()

        return PaperSearchResult(
            title=item.get("title", ""),
            authors=self._normalize_authors(item.get("authors", [])),
            year=item.get("year"),
            doi=item.get("doi"),
            url=item.get("url"),
            abstract=item.get("abstract", ""),
            source="semantic_scholar",
            citations_count=item.get("citationCount"),
            venue=item.get("venue"),
        )

    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """Get papers that cite this paper.

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum citations

        Returns:
            List of citing papers
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/paper/{paper_id}/citations",
                params={
                    "limit": limit,
                    "fields": "paperId,title,authors,year,doi,url,abstract",
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("data", []):
            citing_paper = item.get("citingPaper", {})
            results.append(
                PaperSearchResult(
                    title=citing_paper.get("title", ""),
                    authors=self._normalize_authors(citing_paper.get("authors", [])),
                    year=citing_paper.get("year"),
                    doi=citing_paper.get("doi"),
                    url=citing_paper.get("url"),
                    abstract=citing_paper.get("abstract", ""),
                    source="semantic_scholar",
                )
            )

        return results
```

**Step 3: 运行测试**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/unit/literature/external/test_semantic_scholar.py -v`
Expected: PASS

**Step 4: 提交**

```bash
git add src/academic/literature/external/semantic_scholar.py tests/unit/literature/external/test_semantic_scholar.py
git commit -m "feat(literature): add Semantic Scholar API client

- Implement search, get_by_doi, get_citations
- Use httpx for async HTTP requests
- Return unified PaperSearchResult model

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: 实现 arXiv 客户端

**Files:**
- Create: `backend/src/academic/literature/external/arxiv.py`
- Test: `backend/tests/unit/literature/external/test_arxiv.py`

**Step 1: 实现 ArxivClient (类似 Task 6 的模式)**

```python
# src/academic/literature/external/arxiv.py
"""arXiv API client."""

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from .base import ExternalDBBase, PaperSearchResult

logger = logging.getLogger(__name__)

# arXiv API base URL
API_BASE = "http://export.arxiv.org/api/query"


class ArxivClient(ExternalDBBase):
    """Client for arXiv API."""

    @property
    def name(self) -> str:
        return "arxiv"

    @property
    def display_name(self) -> str:
        return "arXiv"

    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search arXiv for papers.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of search results
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                API_BASE,
                params={
                    "search_query": f"all:{query}",
                    "start": 0,
                    "max_results": limit,
                },
            )
            response.raise_for_status()

        return self._parse_arxiv_response(response.text)

    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI (arXiv ID).

        Args:
            doi: arXiv DOI or ID

        Returns:
            Paper if found, None otherwise
        """
        # Extract arXiv ID from DOI if present
        arxiv_id = doi
        if "arXiv" in doi:
            arxiv_id = doi.split("arXiv.")[-1]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                API_BASE,
                params={
                    "id_list": arxiv_id,
                    "max_results": 1,
                },
            )
            response.raise_for_status()

        results = self._parse_arxiv_response(response.text)
        return results[0] if results else None

    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """arXiv does not support citations lookup.

        Args:
            paper_id: arXiv paper ID
            limit: Ignored

        Returns:
            Empty list (not supported by arXiv API)
        """
        logger.warning("arXiv does not support citations lookup")
        return []

    def _parse_arxiv_response(self, xml_text: str) -> list[PaperSearchResult]:
        """Parse arXiv XML response.

        Args:
            xml_text: XML response from arXiv API

        Returns:
            List of PaperSearchResult
        """
        results = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                published = entry.find("atom:published", ns)
                link = entry.find("atom:id", ns)

                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.find("atom:name", ns)
                    if name is not None:
                        authors.append(name.text)

                year = None
                if published is not None and published.text:
                    year = int(published.text[:4])

                results.append(
                    PaperSearchResult(
                        title=title.text if title is not None else "",
                        authors=authors,
                        year=year,
                        doi=None,
                        url=link.text if link is not None else None,
                        abstract=summary.text if summary is not None else "",
                        source="arxiv",
                    )
                )
        except ET.ParseError as e:
            logger.error(f"Failed to parse arXiv response: {e}")

        return results
```

**Step 2: 提交**

```bash
git add src/academic/literature/external/arxiv.py tests/unit/literature/external/test_arxiv.py
git commit -m "feat(literature): add arXiv API client

- Implement search with XML parsing
- Support DOI/ID lookup
- Citations not supported by arXiv API

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: 实现 Crossref 和 OpenAlex 客户端

**Files:**
- Create: `backend/src/academic/literature/external/crossref.py`
- Create: `backend/src/academic/literature/external/openalex.py`

**Step 1: 实现 CrossrefClient**

```python
# src/academic/literature/external/crossref.py
"""Crossref API client."""

import logging
import httpx
from .base import ExternalDBBase, PaperSearchResult

logger = logging.getLogger(__name__)
API_BASE = "https://api.crossref.org"


class CrossrefClient(ExternalDBBase):
    """Client for Crossref DOI API."""

    @property
    def name(self) -> str:
        return "crossref"

    @property
    def display_name(self) -> str:
        return "Crossref"

    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search Crossref for papers."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/works",
                params={"query": query, "rows": limit},
                headers={"User-Agent": "AcademiaGPT/2.0 (mailto:contact@example.com)"},
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("message", {}).get("items", []):
            results.append(
                PaperSearchResult(
                    title=item.get("title", [""])[0] if item.get("title") else "",
                    authors=self._normalize_authors(item.get("author", [])),
                    year=item.get("published-print", {}).get("date-parts", [[None]])[0][0],
                    doi=item.get("DOI"),
                    url=item.get("URL"),
                    abstract=item.get("abstract", ""),
                    source="crossref",
                    citations_count=item.get("is-referenced-by-count"),
                    venue=item.get("container-title", [""])[0] if item.get("container-title") else None,
                )
            )
        return results

    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/works/{doi}",
                headers={"User-Agent": "AcademiaGPT/2.0"},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            item = response.json().get("message", {})

        return PaperSearchResult(
            title=item.get("title", [""])[0] if item.get("title") else "",
            authors=self._normalize_authors(item.get("author", [])),
            year=item.get("published-print", {}).get("date-parts", [[None]])[0][0],
            doi=item.get("DOI"),
            url=item.get("URL"),
            abstract=item.get("abstract", ""),
            source="crossref",
            citations_count=item.get("is-referenced-by-count"),
        )

    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """Crossref references lookup (not citations)."""
        logger.warning("Crossref does not support direct citations lookup")
        return []
```

**Step 2: 实现 OpenAlexClient**

```python
# src/academic/literature/external/openalex.py
"""OpenAlex API client."""

import logging
import httpx
from .base import ExternalDBBase, PaperSearchResult

logger = logging.getLogger(__name__)
API_BASE = "https://api.openalex.org"


class OpenAlexClient(ExternalDBBase):
    """Client for OpenAlex API."""

    @property
    def name(self) -> str:
        return "openalex"

    @property
    def display_name(self) -> str:
        return "OpenAlex"

    async def search(self, query: str, limit: int = 10) -> list[PaperSearchResult]:
        """Search OpenAlex for papers."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/works",
                params={"search": query, "per_page": limit},
                headers={"mailto": "contact@example.com"},
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("results", []):
            results.append(
                PaperSearchResult(
                    title=item.get("title", ""),
                    authors=[a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])],
                    year=item.get("publication_year"),
                    doi=item.get("doi"),
                    url=item.get("id"),
                    abstract=item.get("abstract", ""),
                    source="openalex",
                    citations_count=item.get("cited_by_count"),
                    venue=item.get("primary_location", {}).get("source", {}).get("display_name"),
                )
            )
        return results

    async def get_by_doi(self, doi: str) -> PaperSearchResult | None:
        """Get paper by DOI."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/works/doi:{doi}",
                headers={"mailto": "contact@example.com"},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            item = response.json()

        return PaperSearchResult(
            title=item.get("title", ""),
            authors=[a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])],
            year=item.get("publication_year"),
            doi=item.get("doi"),
            url=item.get("id"),
            abstract=item.get("abstract", ""),
            source="openalex",
            citations_count=item.get("cited_by_count"),
        )

    async def get_citations(self, paper_id: str, limit: int = 10) -> list[PaperSearchResult]:
        """Get papers that cite this work."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/works/{paper_id}",
                params={"select": "cited_by"},
            )
            # OpenAlex requires additional API calls for citations
            # Simplified: return empty for now
            logger.warning("OpenAlex citations lookup requires pagination")
            return []
```

**Step 3: 更新 external/__init__.py**

```python
# src/academic/literature/external/__init__.py
"""External academic database integration."""

from .base import ExternalDBBase, PaperSearchResult
from .semantic_scholar import SemanticScholarClient
from .arxiv import ArxivClient
from .crossref import CrossrefClient
from .openalex import OpenAlexClient

__all__ = [
    "ExternalDBBase",
    "PaperSearchResult",
    "SemanticScholarClient",
    "ArxivClient",
    "CrossrefClient",
    "OpenAlexClient",
]
```

**Step 4: 提交**

```bash
git add src/academic/literature/external/
git commit -m "feat(literature): add Crossref and OpenAlex clients

- Crossref: DOI lookup and search
- OpenAlex: Comprehensive academic search
- Update __init__.py with all clients

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: 重构 LLM 工具

**Files:**
- Modify: `backend/src/academic/literature/tools.py`

**Step 1: 更新 tools.py**

```python
# src/academic/literature/tools.py
"""LLM tools for literature management."""

import logging
from typing import Literal

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.database.models import Paper, WorkspacePaper
from .navigation.models import PaperTOC
from .navigation.toc_service import TocService
from .navigation.section_loader import SectionLoader
from .external import (
    SemanticScholarClient,
    ArxivClient,
    CrossrefClient,
    OpenAlexClient,
)

logger = logging.getLogger(__name__)


@tool
async def list_papers(workspace_id: str, db: AsyncSession) -> list[dict]:
    """List all papers in a workspace with their TOC.

    Args:
        workspace_id: Workspace ID

    Returns:
        List of papers with their table of contents
    """
    result = await db.execute(
        select(Paper)
        .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
        .where(WorkspacePaper.workspace_id == workspace_id)
    )
    papers = result.scalars().all()

    toc_service = TocService(db)
    paper_list = []

    for paper in papers:
        toc = await toc_service.get_paper_toc(paper.id)
        paper_list.append({
            "paper_id": paper.id,
            "title": paper.title,
            "toc": [
                {"title": e.title, "level": e.level}
                for e in (toc.entries if toc else [])
            ],
        })

    return paper_list


@tool
async def get_section(
    paper_id: str,
    section_title: str,
    db: AsyncSession,
) -> str:
    """Get content of a specific paper section.

    Args:
        paper_id: Paper ID
        section_title: Section title (e.g., "3. Methodology")

    Returns:
        Section content in markdown format
    """
    toc_service = TocService(db)
    section_loader = SectionLoader(db)

    toc = await toc_service.get_paper_toc(paper_id)
    if not toc:
        return f"Paper {paper_id} not found"

    if section_title.lower() == "abstract":
        content = await section_loader.get_abstract(toc)
        return content.content if content else "Abstract not available"

    content = await section_loader.load_section(toc, section_title)
    if not content:
        return f"Section '{section_title}' not found"

    return content.content


@tool
async def search_external(
    query: str,
    source: Literal["semantic_scholar", "arxiv", "crossref", "openalex", "all"] = "all",
) -> list[dict]:
    """Search external academic databases.

    Args:
        query: Search keywords
        source: Database to search (default: all)

    Returns:
        List of matching papers
    """
    clients = {
        "semantic_scholar": SemanticScholarClient(),
        "arxiv": ArxivClient(),
        "crossref": CrossrefClient(),
        "openalex": OpenAlexClient(),
    }

    results = []

    if source == "all":
        # Search all sources
        for name, client in clients.items():
            try:
                found = await client.search(query, limit=5)
                results.extend([r.model_dump() for r in found])
            except Exception as e:
                logger.warning(f"{name} search failed: {e}")
    else:
        client = clients.get(source)
        if client:
            try:
                found = await client.search(query, limit=10)
                results = [r.model_dump() for r in found]
            except Exception as e:
                logger.error(f"{source} search failed: {e}")

    return results


@tool
async def get_paper_by_doi(doi: str) -> dict | None:
    """Get paper metadata by DOI.

    Args:
        doi: Paper DOI

    Returns:
        Paper metadata or None if not found
    """
    clients = [
        SemanticScholarClient(),
        CrossrefClient(),
        OpenAlexClient(),
    ]

    for client in clients:
        try:
            result = await client.get_by_doi(doi)
            if result:
                return result.model_dump()
        except Exception as e:
            logger.debug(f"{client.name} DOI lookup failed: {e}")

    return None
```

**Step 2: 提交**

```bash
git add src/academic/literature/tools.py
git commit -m "feat(literature): refactor LLM tools for TOC navigation

- list_papers: Return papers with TOC structure
- get_section: Load section content by title
- search_external: Multi-database search
- get_paper_by_doi: Cross-database DOI lookup

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: 更新中间件和清理

**Files:**
- Modify: `backend/src/agents/middlewares/literature_context.py`
- Modify: `backend/src/academic/literature/__init__.py`

**Step 1: 更新 literature/__init__.py**

```python
# src/academic/literature/__init__.py
"""Literature module for TOC-based paper navigation."""

from .extraction.pdf_extractor import PDFExtractor
from .navigation import PaperTOC, SectionContent, TOCEntry, TocService, SectionLoader
from .tools import list_papers, get_section, search_external, get_paper_by_doi

__all__ = [
    # Extraction
    "PDFExtractor",
    # Navigation
    "PaperTOC",
    "SectionContent",
    "TOCEntry",
    "TocService",
    "SectionLoader",
    # Tools
    "list_papers",
    "get_section",
    "search_external",
    "get_paper_by_doi",
]
```

**Step 2: 更新 LiteratureContextMiddleware (如果需要)**

检查并更新 `src/agents/middlewares/literature_context.py` 使用新的 `TocService`

**Step 3: 运行完整测试**

Run: `cd /home/cjz/academiagpt-v2/backend && uv run pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 4: 最终提交**

```bash
git add -A
git commit -m "feat(literature): complete TOC-driven navigation refactor

Breaking changes:
- Removed RAG vector retrieval module
- Replaced with TOC-based navigation

New features:
- TocService for hierarchical TOC extraction
- SectionLoader for on-demand content loading
- 4 external database clients (Semantic Scholar, arXiv, Crossref, OpenAlex)
- Unified LLM tools for paper navigation

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 验收检查清单

- [ ] Task 1: RAG 模块已删除
- [ ] Task 2: Navigation 数据模型已创建
- [ ] Task 3: TocService 测试通过
- [ ] Task 4: SectionLoader 测试通过
- [ ] Task 5: External DB 基类已创建
- [ ] Task 6: Semantic Scholar 客户端可用
- [ ] Task 7: arXiv 客户端可用
- [ ] Task 8: Crossref + OpenAlex 客户端可用
- [ ] Task 9: LLM 工具已重构
- [ ] Task 10: 所有测试通过
