"""Tests for WorkspaceLiterature model."""

from src.database.models.workspace_literature import WorkspaceLiterature


def test_workspace_literature_model_has_required_columns():
    """Test that WorkspaceLiterature has all required columns."""
    columns = {c.name for c in WorkspaceLiterature.__table__.columns}
    required = {
        "id", "workspace_id", "title", "authors", "year", "citations",
        "venue", "quartile", "abstract", "doi", "source", "is_core",
        "created_at", "updated_at",
    }
    assert required.issubset(columns)


def test_workspace_literature_tablename():
    """Test that WorkspaceLiterature has correct table name."""
    assert WorkspaceLiterature.__tablename__ == "workspace_literature"
