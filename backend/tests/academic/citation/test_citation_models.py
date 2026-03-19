"""Tests for Citation model."""

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


class TestCitationModelExport:
    """Tests for Citation model export."""

    def test_citation_exported_from_database_models(self):
        """Test that Citation is exported from database models."""
        from src.database import Citation, CitationType
        assert Citation is not None
        assert CitationType is not None
