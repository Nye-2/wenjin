"""Tests for citation formatters."""


import pytest

from src.academic.citation.formatters.apa import APAFormatter
from src.academic.citation.formatters.base import CitationFormatter


class TestCitationFormatterBase:
    """Tests for CitationFormatter base class."""

    def test_citation_formatter_is_abstract(self):
        """Test that CitationFormatter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            CitationFormatter()

    def test_citation_formatter_has_abstract_methods(self):
        """Test that CitationFormatter defines abstract methods."""
        # Check that the abstract methods exist
        assert hasattr(CitationFormatter, 'style_name')
        assert hasattr(CitationFormatter, 'format_citation')
        assert hasattr(CitationFormatter, 'format_bibliography_entry')
        assert hasattr(CitationFormatter, 'format_authors')


class TestAPAFormatter:
    """Tests for APA formatter."""

    @pytest.fixture
    def formatter(self):
        """Create APA formatter instance."""
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


from src.academic.citation.formatters.chicago import ChicagoFormatter
from src.academic.citation.formatters.ieee import IEEEFormatter
from src.academic.citation.formatters.mla import MLAFormatter


class TestMLAFormatter:
    """Tests for MLA formatter."""

    @pytest.fixture
    def formatter(self):
        return MLAFormatter()

    def test_mla_style_name(self, formatter):
        assert formatter.style_name == "MLA"

    def test_mla_format_authors(self, formatter):
        authors = [{"name": "John Smith"}, {"name": "Jane Doe"}]
        result = formatter.format_authors(authors)
        assert "Smith, John" in result
        assert "Jane Doe" in result

    def test_mla_format_bibliography(self, formatter):
        paper = {
            "title": "Test Paper",
            "authors": [{"name": "John Smith"}],
            "year": 2024,
            "venue": "Test Journal",
            "doi": "10.1234/test",
        }
        result = formatter.format_bibliography_entry(paper)
        assert "Smith, John" in result
        assert "Test Paper" in result
        assert "2024" in result
        assert "Test Journal" in result


class TestChicagoFormatter:
    """Tests for Chicago formatter."""

    @pytest.fixture
    def formatter(self):
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
        return IEEEFormatter()

    def test_ieee_style_name(self, formatter):
        assert formatter.style_name == "IEEE"

    def test_ieee_format_authors(self, formatter):
        authors = [{"name": "John Smith"}, {"name": "Jane Doe"}]
        result = formatter.format_authors(authors)
        assert "J. Smith" in result
