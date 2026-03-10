# Citation Management System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Build a complete citation management system with multi-format citation formatting, BibTeX import/export, citation relationship storage, and LLM tools.

**Architecture:** Layered architecture with Citation model at the database layer, CitationService for business logic, formatters for citation styles, BibTeX parser/exporter for interoperability, and LangChain tools for LLM integration.

**Tech Stack:** SQLAlchemy 2.0 async, LangChain tools, Python 3.11+, Pytest for testing

---

## Phase 1: Data Model

### Task 1: Create CitationType Enum and Citation Model

**Files:**
- Create: `src/database/models/citation.py`
- Test: `tests/academic/citation/test_models.py`

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_models.py
"""Tests for Citation model."""

import pytest
from src.database.models.citation import Citation, CitationType


class TestCitationType:
    """Tests for CitationType enum."""

    def test_citation_type_values(self):
        """Test that CitationType has expected values."""
        assert CitationType.EXPLICIT == "explicit"
        assert CitationType.IMPLICIT == "implicit"
        assert CitationType.SELF == "self"
        assert CitationType.SECONDARY == "secondary"


class TestCitationModel:
    """Tests for Citation model."""

    def test_citation_model_creation(self):
        """Test that Citation model can be instantiated."""
        citation = Citation(
            paper_id="paper-123",
            cited_paper_id="paper-456",
            workspace_id="workspace-789",
            citation_type=CitationType.EXPLICIT,
        )
        assert citation.paper_id == "paper-123"
        assert citation.cited_paper_id == "paper-456"
        assert citation.workspace_id == "workspace-789"
        assert citation.citation_type == CitationType.EXPLICIT

    def test_citation_model_with_context(self):
        """Test Citation with optional context fields."""
        citation = Citation(
            paper_id="paper-123",
            cited_paper_id="paper-456",
            workspace_id="workspace-789",
            citation_context="This was shown by Smith et al.",
            section="Related Work",
            page_number=5,
        )
        assert citation.citation_context == "This was shown by Smith et al."
        assert citation.section == "Related Work"
        assert citation.page_number == 5

    def test_citation_default_type(self):
        """Test that default citation type is EXPLICIT."""
        citation = Citation(
            paper_id="paper-123",
            cited_paper_id="paper-456",
            workspace_id="workspace-789",
        )
        assert citation.citation_type == CitationType.EXPLICIT
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_models.py -v`
Expected: FAIL with "No module named 'src.database.models.citation'"

**Step 3: Write minimal implementation**

```python
# src/database/models/citation.py
"""Citation model for tracking paper citation relationships."""

import enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .paper import Paper
    from .workspace import Workspace


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
    )

    section: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

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

    def __repr__(self) -> str:
        return f"<Citation(paper={self.paper_id}, cited={self.cited_paper_id})>"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/database/models/citation.py tests/academic/citation/test_models.py
git commit -m "feat(citation): add Citation model and CitationType enum"
```

---

### Task 2: Export Citation Model from Package

**Files:**
- Modify: `src/database/models/__init__.py:1-30`

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_models.py (add to existing file)

class TestCitationModelExport:
    """Tests for Citation model export."""

    def test_citation_exported_from_database_models(self):
        """Test that Citation is exported from database models."""
        from src.database import Citation, CitationType
        assert Citation is not None
        assert CitationType is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_models.py::TestCitationModelExport -v`
Expected: FAIL with "cannot import name 'Citation'"

**Step 3: Write minimal implementation**

```python
# src/database/models/__init__.py (add Citation import and export)
# Add to imports:
from .citation import Citation, CitationType

# Add to __all__:
    # Citation
    "Citation",
    "CitationType",
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_models.py::TestCitationModelExport -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/database/models/__init__.py tests/academic/citation/test_models.py
git commit -m "feat(citation): export Citation model from database package"
```

---

### Task 3: Add Citation Relationships to Paper Model

**Files:**
- Modify: `src/database/models/paper.py:77-96`
- Test: `tests/academic/citation/test_paper_citations.py`

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_paper_citations.py
"""Tests for Paper citation relationships."""

import pytest
from unittest.mock import MagicMock
from src.database import Paper


class TestPaperCitationRelationships:
    """Tests for Paper citation relationships."""

    def test_paper_has_outgoing_citations_relationship(self):
        """Test that Paper has outgoing_citations relationship."""
        # Check that the relationship exists on the model
        assert hasattr(Paper, "outgoing_citations")

    def test_paper_has_incoming_citations_relationship(self):
        """Test that Paper has incoming_citations relationship."""
        assert hasattr(Paper, "incoming_citations")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_paper_citations.py -v`
Expected: FAIL with "AssertionError" (attribute not found)

**Step 3: Write minimal implementation**

```python
# src/database/models/paper.py
# Add TYPE_CHECKING import for Citation
if TYPE_CHECKING:
    from .workspace import Workspace
    from .citation import Citation  # Add this

# Add to Paper class after existing relationships (around line 97):
    # Citation relationships
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

**Step 4: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_paper_citations.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/database/models/paper.py tests/academic/citation/test_paper_citations.py
git commit -m "feat(citation): add citation relationships to Paper model"
```

---

## Phase 2: Citation Formatters

### Task 4: Create Base Citation Formatter

**Files:**
- Create: `src/academic/citation/__init__.py`
- Create: `src/academic/citation/formatters/__init__.py`
- Create: `src/academic/citation/formatters/base.py`
- Test: `tests/academic/citation/test_formatters.py`

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_formatters.py
"""Tests for citation formatters."""

import pytest
from src.academic.citation.formatters.base import CitationFormatter


class TestCitationFormatterBase:
    """Tests for CitationFormatter base class."""

    def test_citation_formatter_is_abstract(self):
        """Test that CitationFormatter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            CitationFormatter()

    def test_citation_formatter_has_style_name(self):
        """Test that subclasses must implement style_name."""
        from src.academic.citation.formatters.apa import APAFormatter
        formatter = APAFormatter()
        assert formatter.style_name == "APA"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_formatters.py -v`
Expected: FAIL with "No module named 'src.academic.citation'"

**Step 3: Write minimal implementation**

```python
# src/academic/citation/__init__.py
"""Citation management module."""

```

```python
# src/academic/citation/formatters/__init__.py
"""Citation formatters for various academic styles."""

from .base import CitationFormatter
from .apa import APAFormatter

__all__ = ["CitationFormatter", "APAFormatter"]
```

```python
# src/academic/citation/formatters/base.py
"""Base class for citation formatters."""

from abc import ABC, abstractmethod


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
        if not authors:
            return ""
        return ", ".join(a.get("name", "") for a in authors)
```

**Step 4: Run test to verify it fails (APAFormatter not yet implemented)**

Run: `pytest tests/academic/citation/test_formatters.py -v`
Expected: FAIL with "cannot import name 'APAFormatter'"

**Step 5: Commit (partial - base class)**

```bash
git add src/academic/citation/__init__.py src/academic/citation/formatters/__init__.py src/academic/citation/formatters/base.py tests/academic/citation/test_formatters.py
git commit -m "feat(citation): add base CitationFormatter abstract class"
```

---

### Task 5: Create APA Formatter

**Files:**
- Create: `src/academic/citation/formatters/apa.py`
- Test: `tests/academic/citation/test_formatters.py` (extend)

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_formatters.py (add to existing file)

class TestAPAFormatter:
    """Tests for APA formatter."""

    @pytest.fixture
    def formatter(self):
        """Create APA formatter instance."""
        from src.academic.citation.formatters.apa import APAFormatter
        return APAFormatter()

    @pytest.fixture
    def sample_paper(self):
        """Sample paper data."""
        return {
            "title": "Attention Is All You Need",
            "authors": [
                {"name": "Ashish Vaswani"},
                {"name": "Noam Shazeer"},
                {"name": "Niki Parmar"},
            ],
            "year": 2017,
            "venue": "Advances in Neural Information Processing Systems",
            "doi": "10.48550/arXiv.1706.03762",
        }

    def test_apa_style_name(self, formatter):
        """Test APA style name."""
        assert formatter.style_name == "APA"

    def test_apa_format_authors_single(self, formatter):
        """Test APA author formatting with single author."""
        authors = [{"name": "John Smith"}]
        result = formatter.format_authors(authors)
        assert result == "Smith, J."

    def test_apa_format_authors_two(self, formatter):
        """Test APA author formatting with two authors."""
        authors = [{"name": "John Smith"}, {"name": "Jane Doe"}]
        result = formatter.format_authors(authors)
        assert result == "Smith, J. & Doe, J."

    def test_apa_format_authors_multiple(self, formatter):
        """Test APA author formatting with multiple authors."""
        authors = [
            {"name": "John Smith"},
            {"name": "Jane Doe"},
            {"name": "Bob Wilson"},
        ]
        result = formatter.format_authors(authors)
        assert result == "Smith, J., Doe, J., & Wilson, B."

    def test_apa_format_bibliography(self, formatter, sample_paper):
        """Test APA bibliography entry formatting."""
        result = formatter.format_bibliography_entry(sample_paper)
        assert "Vaswani, A." in result
        assert "(2017)" in result
        assert "Attention Is All You Need" in result
        assert "10.48550/arXiv.1706.03762" in result

    def test_apa_format_in_text_single_author(self, formatter):
        """Test APA in-text citation with single author."""
        paper = {"authors": [{"name": "John Smith"}], "year": 2024}
        result = formatter.format_citation(paper, in_text=True)
        assert result == "(Smith, 2024)"

    def test_apa_format_in_text_multiple_authors(self, formatter, sample_paper):
        """Test APA in-text citation with multiple authors."""
        result = formatter.format_citation(sample_paper, in_text=True)
        assert result == "(Vaswani et al., 2017)"

    def test_apa_format_no_year(self, formatter):
        """Test APA formatting when year is missing."""
        paper = {"title": "Untitled", "authors": [{"name": "John Smith"}]}
        result = formatter.format_citation(paper, in_text=True)
        assert "n.d." in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_formatters.py::TestAPAFormatter -v`
Expected: FAIL with various assertion errors

**Step 3: Write minimal implementation**

```python
# src/academic/citation/formatters/apa.py
"""APA 7th Edition citation formatter."""

from .base import CitationFormatter


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
        """Get last name of first author."""
        if not authors:
            return "Unknown"
        name = authors[0].get("name", "")
        return name.split()[-1] if name else "Unknown"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_formatters.py::TestAPAFormatter -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add src/academic/citation/formatters/apa.py tests/academic/citation/test_formatters.py
git commit -m "feat(citation): add APA 7th Edition formatter"
```

---

### Task 6: Create MLA, Chicago, and IEEE Formatters

**Files:**
- Create: `src/academic/citation/formatters/mla.py`
- Create: `src/academic/citation/formatters/chicago.py`
- Create: `src/academic/citation/formatters/ieee.py`
- Modify: `src/academic/citation/formatters/__init__.py`
- Test: `tests/academic/citation/test_formatters.py` (extend)

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_formatters.py (add to existing file)

class TestMLAFormatter:
    """Tests for MLA formatter."""

    @pytest.fixture
    def formatter(self):
        from src.academic.citation.formatters.mla import MLAFormatter
        return MLAFormatter()

    def test_mla_style_name(self, formatter):
        assert formatter.style_name == "MLA"

    def test_mla_format_authors(self, formatter):
        authors = [{"name": "John Smith"}, {"name": "Jane Doe"}]
        result = formatter.format_authors(authors)
        assert "Smith, John" in result
        assert "Doe, Jane" in result


class TestChicagoFormatter:
    """Tests for Chicago formatter."""

    @pytest.fixture
    def formatter(self):
        from src.academic.citation.formatters.chicago import ChicagoFormatter
        return ChicagoFormatter()

    def test_chicago_style_name(self, formatter):
        assert formatter.style_name == "Chicago"

    def test_chicago_format_bibliography(self, formatter):
        paper = {
            "title": "Test Paper",
            "authors": [{"name": "John Smith"}],
            "year": 2024,
            "venue": "Test Journal",
        }
        result = formatter.format_bibliography_entry(paper)
        assert "Smith, John" in result
        assert "2024" in result


class TestIEEEFormatter:
    """Tests for IEEE formatter."""

    @pytest.fixture
    def formatter(self):
        from src.academic.citation.formatters.ieee import IEEEFormatter
        return IEEEFormatter()

    def test_ieee_style_name(self, formatter):
        assert formatter.style_name == "IEEE"

    def test_ieee_format_authors(self, formatter):
        authors = [{"name": "John Smith"}, {"name": "Jane Doe"}]
        result = formatter.format_authors(authors)
        assert "J. Smith" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_formatters.py::TestMLAFormatter -v`
Expected: FAIL with "cannot import name 'MLAFormatter'"

**Step 3: Write minimal implementation**

```python
# src/academic/citation/formatters/mla.py
"""MLA 9th Edition citation formatter."""

from .base import CitationFormatter


class MLAFormatter(CitationFormatter):
    """MLA 9th Edition citation formatter."""

    @property
    def style_name(self) -> str:
        return "MLA"

    def format_authors(self, authors: list[dict]) -> str:
        """MLA author format: Smith, John, and Jane Doe."""
        if not authors:
            return ""

        formatted = []
        for i, author in enumerate(authors):
            name = author.get("name", "")
            if i == 0:
                # First author: Last, First
                parts = name.split()
                if len(parts) >= 2:
                    formatted.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
                else:
                    formatted.append(name)
            else:
                # Other authors: First Last
                formatted.append(name)

        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]}, and {formatted[1]}"
        else:
            return f"{formatted[0]}, et al"

    def format_citation(self, paper: dict, in_text: bool = False) -> str:
        """Format MLA citation."""
        authors = paper.get("authors", [])
        year = paper.get("year")

        if in_text:
            first_author = self._get_first_author_lastname(authors)
            if len(authors) > 1:
                return f"({first_author} et al.)"
            return f"({first_author})"

        return self.format_bibliography_entry(paper)

    def format_bibliography_entry(self, paper: dict) -> str:
        """Format MLA works cited entry."""
        parts = []

        # Authors
        authors = paper.get("authors", [])
        parts.append(self.format_authors(authors))

        # Title (in quotes for articles)
        title = paper.get("title", "")
        parts.append(f'"{title}."')

        # Container (journal)
        venue = paper.get("venue")
        if venue:
            parts.append(f"*{venue}*,")

        # Year
        year = paper.get("year")
        if year:
            parts.append(f"{year},")

        # DOI or URL
        doi = paper.get("doi")
        if doi:
            parts.append(f"doi:{doi}.")

        return " ".join(parts)

    def _get_first_author_lastname(self, authors: list[dict]) -> str:
        if not authors:
            return "Unknown"
        name = authors[0].get("name", "")
        return name.split()[-1] if name else "Unknown"
```

```python
# src/academic/citation/formatters/chicago.py
"""Chicago 17th Edition citation formatter."""

from .base import CitationFormatter


class ChicagoFormatter(CitationFormatter):
    """Chicago 17th Edition citation formatter."""

    @property
    def style_name(self) -> str:
        return "Chicago"

    def format_authors(self, authors: list[dict]) -> str:
        """Chicago author format: Smith, John, and Jane Doe."""
        if not authors:
            return ""

        formatted = []
        for i, author in enumerate(authors):
            name = author.get("name", "")
            if i == 0:
                parts = name.split()
                if len(parts) >= 2:
                    formatted.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
                else:
                    formatted.append(name)
            else:
                formatted.append(name)

        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]}, and {formatted[1]}"
        else:
            return ", ".join(formatted[:-1]) + ", and " + formatted[-1]

    def format_citation(self, paper: dict, in_text: bool = False) -> str:
        """Format Chicago citation."""
        if in_text:
            authors = paper.get("authors", [])
            year = paper.get("year")
            first_author = self._get_first_author_lastname(authors)
            if year:
                return f"({first_author} {year})"
            return f"({first_author})"

        return self.format_bibliography_entry(paper)

    def format_bibliography_entry(self, paper: dict) -> str:
        """Format Chicago bibliography entry."""
        parts = []

        # Authors
        authors = paper.get("authors", [])
        parts.append(self.format_authors(authors))

        # Year
        year = paper.get("year")
        if year:
            parts.append(f"{year}.")

        # Title
        title = paper.get("title", "")
        parts.append(f'"{title}."')

        # Journal
        venue = paper.get("venue")
        if venue:
            parts.append(f"*{venue}*.")

        # DOI
        doi = paper.get("doi")
        if doi:
            parts.append(f"https://doi.org/{doi}.")

        return " ".join(parts)

    def _get_first_author_lastname(self, authors: list[dict]) -> str:
        if not authors:
            return "Unknown"
        name = authors[0].get("name", "")
        return name.split()[-1] if name else "Unknown"
```

```python
# src/academic/citation/formatters/ieee.py
"""IEEE citation formatter."""

from .base import CitationFormatter


class IEEEFormatter(CitationFormatter):
    """IEEE citation formatter."""

    @property
    def style_name(self) -> str:
        return "IEEE"

    def format_authors(self, authors: list[dict]) -> str:
        """IEEE author format: J. Smith and J. Doe."""
        if not authors:
            return ""

        formatted = []
        for author in authors:
            name = author.get("name", "")
            parts = name.split()
            if len(parts) >= 2:
                initials = ". ".join(p[0].upper() for p in parts[:-1]) + "."
                formatted.append(f"{initials} {parts[-1]}")
            else:
                formatted.append(name)

        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]} and {formatted[1]}"
        else:
            return ", ".join(formatted[:-1]) + ", and " + formatted[-1]

    def format_citation(self, paper: dict, in_text: bool = False) -> str:
        """Format IEEE citation."""
        if in_text:
            # IEEE uses numbered citations [1], [2], etc.
            # For simplicity, return author-year format
            authors = paper.get("authors", [])
            year = paper.get("year")
            first_author = self._get_first_author_lastname(authors)
            if year:
                return f"[{first_author}, {year}]"
            return f"[{first_author}]"

        return self.format_bibliography_entry(paper)

    def format_bibliography_entry(self, paper: dict) -> str:
        """Format IEEE reference entry."""
        parts = []

        # Authors
        authors = paper.get("authors", [])
        parts.append(self.format_authors(authors) + ",")

        # Title (in quotes)
        title = paper.get("title", "")
        parts.append(f'"{title},"')

        # Journal (italicized)
        venue = paper.get("venue")
        if venue:
            parts.append(f"*{venue}*,")

        # Year
        year = paper.get("year")
        if year:
            parts.append(f"{year}.")

        # DOI
        doi = paper.get("doi")
        if doi:
            parts.append(f"doi: {doi}.")

        return " ".join(parts)

    def _get_first_author_lastname(self, authors: list[dict]) -> str:
        if not authors:
            return "Unknown"
        name = authors[0].get("name", "")
        return name.split()[-1] if name else "Unknown"
```

**Step 4: Update formatters/__init__.py**

```python
# src/academic/citation/formatters/__init__.py
"""Citation formatters for various academic styles."""

from .base import CitationFormatter
from .apa import APAFormatter
from .mla import MLAFormatter
from .chicago import ChicagoFormatter
from .ieee import IEEEFormatter

__all__ = [
    "CitationFormatter",
    "APAFormatter",
    "MLAFormatter",
    "ChicagoFormatter",
    "IEEEFormatter",
]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_formatters.py -v`
Expected: PASS (all formatter tests)

**Step 6: Commit**

```bash
git add src/academic/citation/formatters/ tests/academic/citation/test_formatters.py
git commit -m "feat(citation): add MLA, Chicago, and IEEE formatters"
```

---

## Phase 3: BibTeX Support

### Task 7: Create BibTeX Parser

**Files:**
- Create: `src/academic/citation/bibtex/__init__.py`
- Create: `src/academic/citation/bibtex/parser.py`
- Test: `tests/academic/citation/test_bibtex.py`

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_bibtex.py
"""Tests for BibTeX parser and exporter."""

import pytest
from src.academic.citation.bibtex.parser import BibTeXParser


class TestBibTeXParser:
    """Tests for BibTeX parser."""

    @pytest.fixture
    def parser(self):
        return BibTeXParser()

    @pytest.fixture
    def sample_bibtex(self):
        return """
@article{vaswani2017attention,
  author = {Ashish Vaswani and Noam Shazeer and Niki Parmar},
  title = {Attention Is All You Need},
  journal = {Advances in Neural Information Processing Systems},
  year = {2017},
  doi = {10.48550/arXiv.1706.03762}
}

@inproceedings{smith2024test,
  author = {John Smith and Jane Doe},
  title = {A Test Paper},
  booktitle = {Test Conference},
  year = {2024}
}
"""

    def test_parse_entries_count(self, parser, sample_bibtex):
        """Test that parser extracts correct number of entries."""
        entries = parser.parse(sample_bibtex)
        assert len(entries) == 2

    def test_parse_entry_type(self, parser, sample_bibtex):
        """Test that parser extracts entry types."""
        entries = parser.parse(sample_bibtex)
        assert entries[0]["type"] == "article"
        assert entries[1]["type"] == "inproceedings"

    def test_parse_entry_key(self, parser, sample_bibtex):
        """Test that parser extracts entry keys."""
        entries = parser.parse(sample_bibtex)
        assert entries[0]["key"] == "vaswani2017attention"
        assert entries[1]["key"] == "smith2024test"

    def test_parse_entry_fields(self, parser, sample_bibtex):
        """Test that parser extracts entry fields."""
        entries = parser.parse(sample_bibtex)
        assert entries[0]["title"] == "Attention Is All You Need"
        assert entries[0]["year"] == "2017"
        assert entries[0]["doi"] == "10.48550/arXiv.1706.03762"

    def test_to_paper_dict(self, parser):
        """Test conversion of BibTeX entry to paper dict."""
        bibtex_entry = {
            "type": "article",
            "key": "test2024",
            "title": "Test Paper",
            "author": "John Smith and Jane Doe",
            "year": "2024",
            "journal": "Test Journal",
            "doi": "10.1234/test",
        }
        paper = parser.to_paper_dict(bibtex_entry)
        assert paper["title"] == "Test Paper"
        assert len(paper["authors"]) == 2
        assert paper["authors"][0]["name"] == "John Smith"
        assert paper["year"] == 2024
        assert paper["venue"] == "Test Journal"
        assert paper["doi"] == "10.1234/test"
        assert paper["source"] == "bibtex_import"

    def test_parse_authors(self, parser):
        """Test author parsing."""
        authors = parser._parse_authors("John Smith and Jane Doe and Bob Wilson")
        assert len(authors) == 3
        assert authors[0]["name"] == "John Smith"
        assert authors[1]["name"] == "Jane Doe"
        assert authors[2]["name"] == "Bob Wilson"

    def test_parse_year_valid(self, parser):
        """Test year parsing with valid year."""
        year = parser._parse_year("2024")
        assert year == 2024

    def test_parse_year_invalid(self, parser):
        """Test year parsing with invalid year."""
        year = parser._parse_year("invalid")
        assert year is None

    def test_parse_year_none(self, parser):
        """Test year parsing with None."""
        year = parser._parse_year(None)
        assert year is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_bibtex.py -v`
Expected: FAIL with "No module named 'src.academic.citation.bibtex'"

**Step 3: Write minimal implementation**

```python
# src/academic/citation/bibtex/__init__.py
"""BibTeX import/export module."""

from .parser import BibTeXParser
from .exporter import BibTeXExporter

__all__ = ["BibTeXParser", "BibTeXExporter"]
```

```python
# src/academic/citation/bibtex/parser.py
"""BibTeX parser for importing references."""

import re


class BibTeXParser:
    """Parse BibTeX files into structured data."""

    ENTRY_PATTERN = re.compile(
        r"@(\w+)\s*\{\s*([^,]+)\s*,",
        re.MULTILINE
    )

    FIELD_PATTERN = re.compile(
        r"(\w+)\s*=\s*[{\"]([^}\"]+)[}\"]",
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

            # Skip comments and string definitions
            if entry_type in ("comment", "string"):
                continue

            # Find entry body
            start = match.end()
            brace_count = 1
            end = start
            while end < len(content) and brace_count > 0:
                if content[end] == "{":
                    brace_count += 1
                elif content[end] == "}":
                    brace_count -= 1
                end += 1

            body = content[start:end-1]

            # Parse fields
            fields = {"type": entry_type, "key": entry_key}
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
        return {
            "title": bibtex_entry.get("title", ""),
            "authors": self._parse_authors(bibtex_entry.get("author", "")),
            "year": self._parse_year(bibtex_entry.get("year")),
            "venue": bibtex_entry.get("journal") or bibtex_entry.get("booktitle", ""),
            "doi": bibtex_entry.get("doi"),
            "source": "bibtex_import",
        }

    def _parse_authors(self, author_str: str) -> list[dict]:
        """Parse BibTeX author string to list of dicts."""
        authors = []
        for name in author_str.split(" and "):
            name = name.strip()
            if name:
                authors.append({"name": name})
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

**Step 4: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_bibtex.py::TestBibTeXParser -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/academic/citation/bibtex/__init__.py src/academic/citation/bibtex/parser.py tests/academic/citation/test_bibtex.py
git commit -m "feat(citation): add BibTeX parser"
```

---

### Task 8: Create BibTeX Exporter

**Files:**
- Create: `src/academic/citation/bibtex/exporter.py`
- Test: `tests/academic/citation/test_bibtex.py` (extend)

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_bibtex.py (add to existing file)

class TestBibTeXExporter:
    """Tests for BibTeX exporter."""

    @pytest.fixture
    def exporter(self):
        from src.academic.citation.bibtex.exporter import BibTeXExporter
        return BibTeXExporter()

    @pytest.fixture
    def sample_papers(self):
        return [
            {
                "title": "Attention Is All You Need",
                "authors": [
                    {"name": "Ashish Vaswani"},
                    {"name": "Noam Shazeer"},
                ],
                "year": 2017,
                "venue": "NeurIPS",
                "doi": "10.48550/arXiv.1706.03762",
            },
            {
                "title": "A Conference Paper",
                "authors": [{"name": "John Smith"}],
                "year": 2024,
                "venue": "Test Conference",
            },
        ]

    def test_export_creates_bibtex(self, exporter, sample_papers):
        """Test that exporter creates BibTeX format."""
        result = exporter.export(sample_papers)
        assert "@article" in result or "@inproceedings" in result
        assert "title = {Attention Is All You Need}" in result

    def test_export_authors(self, exporter, sample_papers):
        """Test that exporter formats authors correctly."""
        result = exporter.export(sample_papers)
        assert "Ashish Vaswani and Noam Shazeer" in result

    def test_export_year(self, exporter, sample_papers):
        """Test that exporter includes year."""
        result = exporter.export(sample_papers)
        assert "year = {2017}" in result

    def test_export_doi(self, exporter, sample_papers):
        """Test that exporter includes DOI."""
        result = exporter.export(sample_papers)
        assert "doi = {10.48550/arXiv.1706.03762}" in result

    def test_generate_key(self, exporter, sample_papers):
        """Test BibTeX key generation."""
        key = exporter._generate_key(sample_papers[0])
        assert "vaswani" in key.lower()
        assert "2017" in key
        assert "attention" in key.lower()

    def test_determine_type_article(self, exporter):
        """Test entry type detection for journal."""
        paper = {"venue": "Journal of Machine Learning Research"}
        assert exporter._determine_type(paper) == "article"

    def test_determine_type_inproceedings(self, exporter):
        """Test entry type detection for conference."""
        paper = {"venue": "International Conference on Machine Learning"}
        assert exporter._determine_type(paper) == "inproceedings"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_bibtex.py::TestBibTeXExporter -v`
Expected: FAIL with "cannot import name 'BibTeXExporter'"

**Step 3: Write minimal implementation**

```python
# src/academic/citation/bibtex/exporter.py
"""BibTeX exporter for exporting references."""


class BibTeXExporter:
    """Export papers to BibTeX format."""

    ENTRY_TYPES = {
        "article": "article",
        "inproceedings": "inproceedings",
        "book": "book",
        "phdthesis": "phdthesis",
        "mastersthesis": "mastersthesis",
        "misc": "misc",
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

        return "\n\n".join(entries)

    def _format_entry(self, paper: dict) -> str:
        """Format single paper as BibTeX entry."""
        entry_type = self._determine_type(paper)
        key = self._generate_key(paper)

        lines = [f"@{entry_type}{{{key},"]

        # Required fields
        if paper.get("authors"):
            authors = " and ".join(
                a.get("name", "") for a in paper["authors"]
            )
            lines.append(f"  author = {{{authors}}},")

        if paper.get("title"):
            lines.append(f"  title = {{{paper['title']}}},")

        # Optional fields
        if paper.get("year"):
            lines.append(f"  year = {{{paper['year']}}},")

        if paper.get("venue"):
            if entry_type == "article":
                lines.append(f"  journal = {{{paper['venue']}}},")
            elif entry_type == "inproceedings":
                lines.append(f"  booktitle = {{{paper['venue']}}},")

        if paper.get("doi"):
            lines.append(f"  doi = {{{paper['doi']}}},")

        if paper.get("abstract"):
            lines.append(f"  abstract = {{{paper['abstract']}}},")

        lines.append("}")

        return "\n".join(lines)

    def _determine_type(self, paper: dict) -> str:
        """Determine BibTeX entry type from paper metadata."""
        venue = (paper.get("venue") or "").lower()
        if "conference" in venue or "workshop" in venue or "proceedings" in venue:
            return "inproceedings"
        elif "journal" in venue or "transactions" in venue:
            return "article"
        return "misc"

    def _generate_key(self, paper: dict) -> str:
        """Generate BibTeX citation key."""
        parts = []

        # First author lastname
        authors = paper.get("authors", [])
        if authors:
            name = authors[0].get("name", "")
            parts.append(name.split()[-1].lower())

        # Year
        if paper.get("year"):
            parts.append(str(paper["year"]))

        # First word of title
        title = paper.get("title", "")
        if title:
            first_word = "".join(c for c in title.split()[0] if c.isalnum())
            parts.append(first_word.lower())

        return "_".join(parts) if parts else "unknown"
```

**Step 4: Update bibtex/__init__.py (already done in Task 7)**

**Step 5: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_bibtex.py::TestBibTeXExporter -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/academic/citation/bibtex/exporter.py tests/academic/citation/test_bibtex.py
git commit -m "feat(citation): add BibTeX exporter"
```

---

## Phase 4: Citation Service

### Task 9: Create CitationService

**Files:**
- Create: `src/academic/citation/service.py`
- Test: `tests/academic/citation/test_service.py`

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_service.py
"""Tests for CitationService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.citation.service import CitationService
from src.database import Citation, CitationType


class TestCitationServiceInit:
    """Tests for CitationService initialization."""

    def test_init_with_db_session(self):
        """Test that CitationService initializes with database session."""
        mock_db = AsyncMock()
        service = CitationService(mock_db)
        assert service.db == mock_db


class TestAddCitation:
    """Tests for add_citation method."""

    @pytest.fixture
    def mock_db_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        return CitationService(mock_db_session)

    @pytest.fixture
    def sample_ids(self):
        return {
            "paper_id": str(uuid.uuid4()),
            "cited_paper_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
        }

    @pytest.mark.asyncio
    async def test_add_citation_creates_citation(
        self, service, mock_db_session, sample_ids
    ):
        """Test that add_citation creates a Citation object."""
        result = await service.add_citation(**sample_ids)

        mock_db_session.add.assert_called_once()
        added_citation = mock_db_session.add.call_args[0][0]
        assert added_citation.paper_id == sample_ids["paper_id"]
        assert added_citation.cited_paper_id == sample_ids["cited_paper_id"]
        assert added_citation.workspace_id == sample_ids["workspace_id"]

    @pytest.mark.asyncio
    async def test_add_citation_with_context(
        self, service, mock_db_session, sample_ids
    ):
        """Test add_citation with optional context."""
        result = await service.add_citation(
            **sample_ids,
            citation_context="As shown by Smith et al.",
            section="Related Work",
        )

        added_citation = mock_db_session.add.call_args[0][0]
        assert added_citation.citation_context == "As shown by Smith et al."
        assert added_citation.section == "Related Work"


class TestGetCitations:
    """Tests for citation retrieval methods."""

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db_session):
        return CitationService(mock_db_session)

    @pytest.fixture
    def sample_ids(self):
        return {
            "paper_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
        }

    @pytest.mark.asyncio
    async def test_get_outgoing_citations(
        self, service, mock_db_session, sample_ids
    ):
        """Test getting papers cited by a paper."""
        mock_citation = MagicMock(spec=Citation)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_citation]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_outgoing_citations(**sample_ids)

        assert len(result) == 1
        assert result[0] == mock_citation

    @pytest.mark.asyncio
    async def test_get_incoming_citations(
        self, service, mock_db_session, sample_ids
    ):
        """Test getting papers that cite a paper."""
        mock_citation = MagicMock(spec=Citation)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_citation]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.get_incoming_citations(**sample_ids)

        assert len(result) == 1


class TestRemoveCitation:
    """Tests for remove_citation method."""

    @pytest.fixture
    def mock_db_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        return CitationService(mock_db_session)

    @pytest.fixture
    def sample_ids(self):
        return {
            "paper_id": str(uuid.uuid4()),
            "cited_paper_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
        }

    @pytest.mark.asyncio
    async def test_remove_citation_found(
        self, service, mock_db_session, sample_ids
    ):
        """Test removing an existing citation."""
        mock_citation = MagicMock(spec=Citation)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_citation
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.remove_citation(**sample_ids)

        assert result is True
        mock_db_session.delete.assert_called_once_with(mock_citation)

    @pytest.mark.asyncio
    async def test_remove_citation_not_found(
        self, service, mock_db_session, sample_ids
    ):
        """Test removing a non-existent citation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.remove_citation(**sample_ids)

        assert result is False
        mock_db_session.delete.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_service.py -v`
Expected: FAIL with "No module named 'src.academic.citation.service'"

**Step 3: Write minimal implementation**

```python
# src/academic/citation/service.py
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

    async def get_citation_graph(
        self,
        paper_id: str,
        workspace_id: str,
        depth: int = 1,
    ) -> dict:
        """Get citation graph with specified depth.

        Args:
            paper_id: Starting paper ID
            workspace_id: Workspace context
            depth: How many levels of citations to include

        Returns:
            Dict with 'nodes' (paper info) and 'edges' (citation relationships)
        """
        nodes = []
        edges = []
        visited = set()

        async def collect_citations(pid: str, current_depth: int):
            if current_depth > depth or pid in visited:
                return
            visited.add(pid)

            # Get outgoing citations
            outgoing = await self.get_outgoing_citations(pid, workspace_id)
            for citation in outgoing:
                edges.append({
                    "source": str(citation.paper_id),
                    "target": str(citation.cited_paper_id),
                    "type": citation.citation_type,
                })
                await collect_citations(str(citation.cited_paper_id), current_depth + 1)

            # Get incoming citations
            incoming = await self.get_incoming_citations(pid, workspace_id)
            for citation in incoming:
                edges.append({
                    "source": str(citation.paper_id),
                    "target": str(citation.cited_paper_id),
                    "type": citation.citation_type,
                })
                await collect_citations(str(citation.paper_id), current_depth + 1)

        await collect_citations(paper_id, 0)

        # Deduplicate nodes
        unique_ids = set()
        for edge in edges:
            unique_ids.add(edge["source"])
            unique_ids.add(edge["target"])
        unique_ids.add(paper_id)

        nodes = [{"id": pid} for pid in unique_ids]

        return {"nodes": nodes, "edges": edges}

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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/academic/citation/service.py tests/academic/citation/test_service.py
git commit -m "feat(citation): add CitationService with CRUD operations"
```

---

## Phase 5: LLM Tools

### Task 10: Create Citation LLM Tools

**Files:**
- Create: `src/academic/citation/tools.py`
- Modify: `src/agents/lead_agent/agent.py:161-196`
- Test: `tests/academic/citation/test_tools.py`

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_tools.py
"""Tests for citation LLM tools."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFormatCitationTool:
    """Tests for format_citation tool."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def sample_paper_id(self):
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_format_citation_apa(self, mock_db, sample_paper_id):
        """Test format_citation with APA style."""
        from src.academic.citation.tools import format_citation

        # Mock paper
        mock_paper = MagicMock()
        mock_paper.id = sample_paper_id
        mock_paper.title = "Test Paper"
        mock_paper.authors = [{"name": "John Smith"}]
        mock_paper.year = 2024
        mock_paper.venue = "Test Journal"
        mock_paper.doi = "10.1234/test"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_paper
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await format_citation.ainvoke({
            "paper_id": sample_paper_id,
            "style": "apa",
            "db": mock_db,
        })

        assert "Smith" in result
        assert "2024" in result

    @pytest.mark.asyncio
    async def test_format_citation_not_found(self, mock_db):
        """Test format_citation with non-existent paper."""
        from src.academic.citation.tools import format_citation

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await format_citation.ainvoke({
            "paper_id": "non-existent",
            "style": "apa",
            "db": mock_db,
        })

        assert "not found" in result.lower()


class TestFormatBibliographyTool:
    """Tests for format_bibliography tool."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def sample_workspace_id(self):
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_format_bibliography(self, mock_db, sample_workspace_id):
        """Test format_bibliography tool."""
        from src.academic.citation.tools import format_bibliography

        # Mock papers
        mock_paper1 = MagicMock()
        mock_paper1.title = "First Paper"
        mock_paper1.authors = [{"name": "John Smith"}]
        mock_paper1.year = 2024
        mock_paper1.venue = "Test Journal"
        mock_paper1.doi = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper1]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await format_bibliography.ainvoke({
            "workspace_id": sample_workspace_id,
            "style": "apa",
            "db": mock_db,
        })

        assert "First Paper" in result


class TestBibTeXTools:
    """Tests for BibTeX import/export tools."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def sample_workspace_id(self):
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_export_bibtex(self, mock_db, sample_workspace_id):
        """Test export_bibtex tool."""
        from src.academic.citation.tools import export_bibtex

        mock_paper = MagicMock()
        mock_paper.title = "Test Paper"
        mock_paper.authors = [{"name": "John Smith"}]
        mock_paper.year = 2024
        mock_paper.venue = "Test Journal"
        mock_paper.doi = "10.1234/test"
        mock_paper.abstract = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_paper]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await export_bibtex.ainvoke({
            "workspace_id": sample_workspace_id,
            "db": mock_db,
        })

        assert "@article" in result or "@misc" in result
        assert "Test Paper" in result

    @pytest.mark.asyncio
    async def test_import_bibtex(self, mock_db, sample_workspace_id):
        """Test import_bibtex tool."""
        from src.academic.citation.tools import import_bibtex

        bibtex_content = """
@article{test2024,
  author = {John Smith},
  title = {Test Paper},
  journal = {Test Journal},
  year = {2024}
}
"""
        # Mock paper service
        with patch("src.academic.citation.tools.PaperService") as mock_service:
            mock_instance = mock_service.return_value
            mock_paper = MagicMock()
            mock_paper.title = "Test Paper"
            mock_instance.create = AsyncMock(return_value=mock_paper)
            mock_instance.add_to_workspace = AsyncMock()

            result = await import_bibtex.ainvoke({
                "bibtex_content": bibtex_content,
                "workspace_id": sample_workspace_id,
                "db": mock_db,
            })

            assert "imported" in result.lower() or "success" in result.lower()


class TestAddCitationTool:
    """Tests for add_citation tool."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def sample_ids(self):
        return {
            "paper_id": str(uuid.uuid4()),
            "cited_paper_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
        }

    @pytest.mark.asyncio
    async def test_add_citation_tool(self, mock_db, sample_ids):
        """Test add_citation tool."""
        from src.academic.citation.tools import add_citation

        result = await add_citation.ainvoke({
            **sample_ids,
            "citation_context": "As shown in previous work",
            "section": "Related Work",
            "db": mock_db,
        })

        assert "success" in result.lower() or "added" in result.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_tools.py -v`
Expected: FAIL with "No module named 'src.academic.citation.tools'"

**Step 3: Write minimal implementation**

```python
# src/academic/citation/tools.py
"""LLM tools for citation management."""

import logging
from typing import Literal

from langchain_core.tools import tool, InjectedToolArg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Paper, WorkspacePaper, Citation
from src.academic.services.paper_service import PaperService
from .service import CitationService
from .formatters import APAFormatter, MLAFormatter, ChicagoFormatter, IEEEFormatter
from .bibtex import BibTeXParser, BibTeXExporter

logger = logging.getLogger(__name__)

# Formatter registry
FORMATTERS = {
    "apa": APAFormatter,
    "mla": MLAFormatter,
    "chicago": ChicagoFormatter,
    "ieee": IEEEFormatter,
}


def _paper_to_dict(paper: Paper) -> dict:
    """Convert Paper model to dict for formatter."""
    return {
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "abstract": paper.abstract,
    }


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
    result = await db.execute(
        select(Paper).where(Paper.id == paper_id)
    )
    paper = result.scalar_one_or_none()

    if not paper:
        return f"Paper {paper_id} not found"

    formatter = FORMATTERS.get(style, APAFormatter)()
    return formatter.format_citation(_paper_to_dict(paper), in_text=in_text)


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
    result = await db.execute(
        select(Paper)
        .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
        .where(WorkspacePaper.workspace_id == workspace_id)
        .order_by(Paper.title)
    )
    papers = result.scalars().all()

    if not papers:
        return "No papers in workspace"

    formatter = FORMATTERS.get(style, APAFormatter)()
    entries = []

    for i, paper in enumerate(papers, 1):
        entry = formatter.format_bibliography_entry(_paper_to_dict(paper))
        entries.append(f"{i}. {entry}")

    return "\n\n".join(entries)


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
    result = await db.execute(
        select(Paper)
        .join(WorkspacePaper, Paper.id == WorkspacePaper.paper_id)
        .where(WorkspacePaper.workspace_id == workspace_id)
        .order_by(Paper.title)
    )
    papers = result.scalars().all()

    if not papers:
        return "% No papers in workspace"

    exporter = BibTeXExporter()
    paper_dicts = [_paper_to_dict(p) for p in papers]
    return exporter.export(paper_dicts)


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
    parser = BibTeXParser()
    entries = parser.parse(bibtex_content)

    if not entries:
        return "No valid BibTeX entries found"

    paper_service = PaperService(db)
    imported = 0
    errors = []

    for entry in entries:
        try:
            paper_dict = parser.to_paper_dict(entry)
            paper = await paper_service.create(**paper_dict)
            await paper_service.add_to_workspace(
                paper_id=str(paper.id),
                workspace_id=workspace_id,
            )
            imported += 1
        except Exception as e:
            logger.warning(f"Failed to import entry {entry.get('key')}: {e}")
            errors.append(entry.get("key", "unknown"))

    message = f"Successfully imported {imported} paper(s)"
    if errors:
        message += f". Failed to import: {', '.join(errors)}"

    return message


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
    # Get workspace_id from paper's workspace association
    result = await db.execute(
        select(WorkspacePaper.workspace_id)
        .where(WorkspacePaper.paper_id == paper_id)
        .limit(1)
    )
    row = result.first()

    if not row:
        return {"nodes": [], "edges": [], "error": "Paper not found in any workspace"}

    workspace_id = row[0]

    service = CitationService(db)
    return await service.get_citation_graph(paper_id, workspace_id, depth)


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
    # Verify both papers exist
    for pid in [paper_id, cited_paper_id]:
        result = await db.execute(select(Paper.id).where(Paper.id == pid))
        if not result.first():
            return f"Paper {pid} not found"

    service = CitationService(db)
    await service.add_citation(
        paper_id=paper_id,
        cited_paper_id=cited_paper_id,
        workspace_id=workspace_id,
        citation_context=citation_context,
        section=section,
    )

    return f"Successfully added citation from {paper_id} to {cited_paper_id}"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_tools.py -v`
Expected: PASS (most tests)

**Step 5: Commit**

```bash
git add src/academic/citation/tools.py tests/academic/citation/test_tools.py
git commit -m "feat(citation): add LLM tools for citation management"
```

---

### Task 11: Register Citation Tools in Lead Agent

**Files:**
- Modify: `src/agents/lead_agent/agent.py:161-196`

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_tools.py (add to existing file)

class TestCitationToolsRegistration:
    """Tests for citation tools registration in lead agent."""

    def test_citation_tools_in_available_tools(self):
        """Test that citation tools are registered in get_available_tools."""
        from src.agents.lead_agent.agent import get_available_tools

        tools = get_available_tools()
        tool_names = [t.name for t in tools]

        assert "format_citation" in tool_names
        assert "format_bibliography" in tool_names
        assert "export_bibtex" in tool_names
        assert "import_bibtex" in tool_names
        assert "add_citation" in tool_names
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_tools.py::TestCitationToolsRegistration -v`
Expected: FAIL with "AssertionError: 'format_citation' not in tool_names"

**Step 3: Write minimal implementation**

```python
# src/agents/lead_agent/agent.py
# Add after the literature tools import block (around line 195):

    # Citation management tools
    try:
        from src.academic.citation.tools import (
            format_citation,
            format_bibliography,
            export_bibtex,
            import_bibtex,
            get_citation_graph,
            add_citation,
        )
        tools.extend([
            format_citation,
            format_bibliography,
            export_bibtex,
            import_bibtex,
            get_citation_graph,
            add_citation,
        ])
    except ImportError:
        pass  # Citation tools not yet implemented
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_tools.py::TestCitationToolsRegistration -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agents/lead_agent/agent.py tests/academic/citation/test_tools.py
git commit -m "feat(citation): register citation tools in lead agent"
```

---

## Phase 6: Final Verification

### Task 12: Run Full Test Suite

**Files:**
- None (verification task)

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 2: Run citation module tests specifically**

Run: `pytest tests/academic/citation/ -v --cov=src/academic/citation --cov-report=term-missing`
Expected: Coverage > 80%, all tests pass

**Step 3: Commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix(citation): fix any failing tests"
```

---

### Task 13: Update Module Exports and Documentation

**Files:**
- Modify: `src/academic/citation/__init__.py`
- Create: `tests/academic/citation/__init__.py`

**Step 1: Update module exports**

```python
# src/academic/citation/__init__.py
"""Citation management module.

This module provides citation management functionality including:
- Multi-format citation formatting (APA, MLA, Chicago, IEEE)
- BibTeX import/export
- Citation relationship storage and querying
- LLM tools for citation management
"""

from .service import CitationService
from .formatters import (
    CitationFormatter,
    APAFormatter,
    MLAFormatter,
    ChicagoFormatter,
    IEEEFormatter,
)
from .bibtex import BibTeXParser, BibTeXExporter

__all__ = [
    "CitationService",
    "CitationFormatter",
    "APAFormatter",
    "MLAFormatter",
    "ChicagoFormatter",
    "IEEEFormatter",
    "BibTeXParser",
    "BibTeXExporter",
]
```

```python
# tests/academic/citation/__init__.py
"""Tests for citation management module."""

```

**Step 2: Commit**

```bash
git add src/academic/citation/__init__.py tests/academic/citation/__init__.py
git commit -m "docs(citation): update module exports and documentation"
```

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 1-3 | Data Model (Citation model, Paper relationships) |
| 2 | 4-6 | Citation Formatters (Base, APA, MLA, Chicago, IEEE) |
| 3 | 7-8 | BibTeX Support (Parser, Exporter) |
| 4 | 9 | CitationService |
| 5 | 10-11 | LLM Tools + Registration |
| 6 | 12-13 | Verification + Documentation |

**Total: 13 tasks**
