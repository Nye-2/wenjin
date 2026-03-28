"""Tests for workspace full-text search."""


class TestSearchWorkspaceToolDefinition:
    def test_gin_index_defined_on_paper_section(self):
        """Verify the GIN index is defined in the model."""
        from src.database.models.paper import PaperSection
        table_args = PaperSection.__table_args__
        index_names = [idx.name for idx in table_args if hasattr(idx, "name")]
        assert "ix_paper_sections_content_fts" in index_names
