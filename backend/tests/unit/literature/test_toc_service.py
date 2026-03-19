# tests/unit/literature/test_toc_service.py
"""Tests for TocService."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.literature.navigation.models import TOCEntry
from src.academic.literature.navigation.toc_service import TocService


@pytest.fixture
def mock_db():
    """Mock database session."""
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
        # Setup mock paper
        mock_paper = MagicMock()
        mock_paper.id = "paper-123"
        mock_paper.title = "Test Paper"
        mock_paper.abstract = "This is an abstract"

        # Setup mock extraction with full_text
        mock_extraction = MagicMock()
        mock_extraction.structured_data = {
            "full_text": "# 1. Introduction\n\nContent here...\n\n# 2. Methods\n\nMore content..."
        }

        # Setup mock results
        paper_result = MagicMock()
        paper_result.scalar_one_or_none.return_value = mock_paper

        extraction_result = MagicMock()
        extraction_result.scalar_one_or_none.return_value = mock_extraction

        # Configure mock_db.execute to return different results based on query
        call_count = [0]

        def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return paper_result
            else:
                return extraction_result

        mock_db.execute.side_effect = mock_execute

        # Execute
        result = await toc_service.get_paper_toc("paper-123")

        # Assert
        assert result is not None
        assert result.paper_id == "paper-123"
        assert result.title == "Test Paper"
        assert result.abstract == "This is an abstract"
        assert len(result.entries) >= 2  # At least 2 sections detected

    @pytest.mark.asyncio
    async def test_get_paper_toc_returns_none_if_not_found(self, toc_service, mock_db):
        """Test that get_paper_toc returns None for non-existent paper."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await toc_service.get_paper_toc("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_toc_handles_markdown_headers(self, toc_service):
        """Test TOC extraction from markdown headers."""
        text = """# 1. Introduction

Some intro content.

## 1.1 Background

Background info.

# 2. Methods

Methods content.
"""
        entries = toc_service._extract_toc_entries(text)

        assert len(entries) == 2  # Two level-1 sections
        assert entries[0].title == "1. Introduction"
        assert entries[1].title == "2. Methods"
        # Check that 1.1 is a child of 1. Introduction
        assert len(entries[0].children) == 1
        assert entries[0].children[0].title == "1.1 Background"

    @pytest.mark.asyncio
    async def test_build_hierarchy_creates_nested_structure(self, toc_service):
        """Test that hierarchy is built correctly."""
        flat_entries = [
            TOCEntry(title="1. Intro", level=1, char_start=0, char_end=100, children=[]),
            TOCEntry(title="1.1 Sub", level=2, char_start=50, char_end=80, children=[]),
            TOCEntry(title="2. Methods", level=1, char_start=100, char_end=200, children=[]),
        ]

        result = toc_service._build_hierarchy(flat_entries)

        assert len(result) == 2  # Two top-level entries
        assert result[0].title == "1. Intro"
        assert len(result[0].children) == 1
        assert result[0].children[0].title == "1.1 Sub"
        assert result[1].title == "2. Methods"
