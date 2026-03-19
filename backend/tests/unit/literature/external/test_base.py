# tests/unit/literature/external/test_base.py
"""Tests for external database base classes."""

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

    def test_citations_count_optional(self):
        """Test citations_count is optional."""
        result = PaperSearchResult(
            title="Paper",
            source="semantic_scholar",
            citations_count=100,
        )

        assert result.citations_count == 100
