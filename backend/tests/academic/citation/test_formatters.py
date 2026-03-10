"""Tests for citation formatters."""

import pytest
from abc import ABC
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
