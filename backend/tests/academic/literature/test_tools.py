"""Tests for literature navigation tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.academic.literature.tools import (
    GetPaperTocInput,
    GetPaperSectionInput,
    SearchPapersInput,
    _get_paper_by_id,
    _get_section_by_path,
    _search_papers_in_db,
    format_toc_output,
    format_section_output,
    format_search_results,
)
from src.database import Paper, PaperSection


class TestHelperFunctions:
    """Tests for helper functions that don't require database session."""

    def test_format_toc_output_with_toc(self):
        """Test formatting TOC output with valid TOC."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.title = "Attention Is All You Need"
        mock_paper.year = 2017
        mock_paper.toc = [
            {"number": "1", "title": "Introduction", "level": 1},
            {"number": "2", "title": "Background", "level": 1},
            {"number": "3", "title": "Model Architecture", "level": 1},
            {"number": "3.1", "title": "Encoder", "level": 2},
            {"number": "3.2", "title": "Decoder", "level": 2},
        ]

        result = format_toc_output(mock_paper)

        assert "Attention Is All You Need" in result
        assert "(2017)" in result
        assert "1. Introduction" in result
        assert "2. Background" in result
        assert "3. Model Architecture" in result
        assert "  3.1. Encoder" in result  # Indented for level 2
        assert "  3.2. Decoder" in result

    def test_format_toc_output_without_toc(self):
        """Test formatting TOC output when paper has no TOC."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.title = "Test Paper"
        mock_paper.year = 2024
        mock_paper.toc = None

        result = format_toc_output(mock_paper)

        assert "No table of contents available" in result
        assert "Test Paper" in result

    def test_format_toc_output_empty_toc(self):
        """Test formatting TOC output when TOC is empty list."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.title = "Test Paper"
        mock_paper.year = 2024
        mock_paper.toc = []

        result = format_toc_output(mock_paper)

        assert "No table of contents available" in result

    def test_format_section_output(self):
        """Test formatting section output."""
        mock_section = MagicMock(spec=PaperSection)
        mock_section.section_title = "Model Architecture"
        mock_section.section_path = "3"
        mock_section.page_start = 5
        mock_section.page_end = 8
        mock_section.content = "The Transformer uses multi-head attention..."

        result = format_section_output(mock_section)

        assert "## Model Architecture" in result
        assert "**Section:** 3" in result
        assert "**Pages:** 5-8" in result
        assert "multi-head attention" in result

    def test_format_search_results_with_papers(self):
        """Test formatting search results with papers."""
        mock_paper1 = MagicMock(spec=Paper)
        mock_paper1.id = "paper-1"
        mock_paper1.title = "Attention Is All You Need"
        mock_paper1.year = 2017
        mock_paper1.venue = "NeurIPS"
        mock_paper1.author_names = ["Vaswani", "Shazeer", "Parmar", "Uszkoreit"]

        mock_paper2 = MagicMock(spec=Paper)
        mock_paper2.id = "paper-2"
        mock_paper2.title = "BERT"
        mock_paper2.year = 2019
        mock_paper2.venue = "NAACL"
        mock_paper2.author_names = ["Devlin", "Chang"]

        papers = [mock_paper1, mock_paper2]
        result = format_search_results(papers, "transformer", None)

        assert "2 paper" in result.lower()
        assert "Attention Is All You Need" in result
        assert "BERT" in result
        assert "NeurIPS" in result
        assert "NAACL" in result
        assert "Vaswani" in result
        assert "et al." in result  # More than 3 authors

    def test_format_search_results_no_papers(self):
        """Test formatting search results with no papers."""
        result = format_search_results([], "nonexistent", None)

        assert "No papers found" in result
        assert "nonexistent" in result

    def test_format_search_results_with_workspace(self):
        """Test formatting search results with workspace scope."""
        mock_paper = MagicMock(spec=Paper)
        mock_paper.id = "paper-1"
        mock_paper.title = "Test Paper"
        mock_paper.year = 2024
        mock_paper.venue = "Test Venue"
        mock_paper.author_names = ["Author One"]

        papers = [mock_paper]
        result = format_search_results(papers, "test", "ws-123")

        assert "Test Paper" in result


class TestInputSchemas:
    """Tests for tool input schemas."""

    def test_get_paper_toc_input_schema(self):
        """Test GetPaperTocInput schema validation."""
        input_data = GetPaperTocInput(paper_id="paper-123")
        assert input_data.paper_id == "paper-123"

    def test_get_paper_section_input_schema(self):
        """Test GetPaperSectionInput schema validation."""
        input_data = GetPaperSectionInput(
            paper_id="paper-123",
            section_path="3.2.1",
        )
        assert input_data.paper_id == "paper-123"
        assert input_data.section_path == "3.2.1"

    def test_search_papers_input_schema(self):
        """Test SearchPapersInput schema validation."""
        input_data = SearchPapersInput(query="transformer", workspace_id="ws-123")
        assert input_data.query == "transformer"
        assert input_data.workspace_id == "ws-123"

    def test_search_papers_input_optional_workspace(self):
        """Test SearchPapersInput with optional workspace_id."""
        input_data = SearchPapersInput(query="transformer")
        assert input_data.query == "transformer"
        assert input_data.workspace_id is None


class TestPaperModelWithToc:
    """Tests for Paper model with TOC field."""

    def test_paper_with_toc(self):
        """Test Paper model with TOC field."""
        paper = Paper(
            title="Test Paper",
            authors=[{"name": "Author One"}],
            year=2024,
            toc=[
                {"number": "1", "title": "Introduction", "level": 1},
                {"number": "2", "title": "Methods", "level": 1},
            ],
        )
        assert paper.toc is not None
        assert len(paper.toc) == 2
        assert paper.toc[0]["title"] == "Introduction"

    def test_paper_without_toc(self):
        """Test Paper model without TOC field (nullable)."""
        paper = Paper(
            title="Test Paper",
            authors=[{"name": "Author One"}],
            year=2024,
        )
        assert paper.toc is None


class TestPaperSectionModel:
    """Tests for PaperSection model."""

    def test_paper_section_instantiation(self):
        """Test PaperSection model can be instantiated."""
        section = PaperSection(
            paper_id="paper-123",
            workspace_id="ws-456",
            section_title="Model Architecture",
            section_path="3",
            page_start=5,
            page_end=8,
            content="The Transformer model architecture...",
            level=1,
        )
        assert section.paper_id == "paper-123"
        assert section.workspace_id == "ws-456"
        assert section.section_title == "Model Architecture"
        assert section.section_path == "3"
        assert section.page_start == 5
        assert section.page_end == 8
        assert section.level == 1

    def test_paper_section_nested_path(self):
        """Test PaperSection with nested section path."""
        section = PaperSection(
            paper_id="paper-123",
            workspace_id="ws-456",
            section_title="Encoder Stack",
            section_path="3.1.2",
            page_start=6,
            page_end=7,
            content="Nested section content...",
            level=3,
        )
        assert section.section_path == "3.1.2"
        assert section.level == 3
