# tests/unit/literature/test_section_loader.py
"""Tests for SectionLoader."""

from unittest.mock import AsyncMock, MagicMock

import pytest

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
        abstract="This is the abstract text.",
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
        # Setup mock - simulate full_text with character positions
        full_text = "Introduction content here..." + "X" * 70 + "Methods section content..." + "Y" * 165

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = {"full_text": full_text}
        mock_db.execute.return_value = mock_result

        # Execute
        result = await section_loader.load_section(sample_toc, "1. Introduction")

        # Assert
        assert result is not None
        assert result.section_title == "1. Introduction"
        assert result.paper_id == "paper-123"
        assert result.has_subsections is False

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
        assert result.content == "This is the abstract text."
        assert result.has_subsections is False

    @pytest.mark.asyncio
    async def test_load_section_handles_subsections(self, section_loader, mock_db, sample_toc):
        """Test loading section with subsections."""
        full_text = "X" * 100 + "Methods content" + "Y" * 185

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = {"full_text": full_text}
        mock_db.execute.return_value = mock_result

        result = await section_loader.load_section(sample_toc, "2. Methods")

        assert result is not None
        assert result.has_subsections is True
