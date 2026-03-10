"""Tests for Paper citation relationships."""

import pytest
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
