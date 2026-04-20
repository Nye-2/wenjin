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


def test_workspace_literature_has_hot_path_indexes() -> None:
    index_names = {idx.name for idx in WorkspaceLiterature.__table__.indexes}
    assert "ix_workspace_literature_workspace_created" in index_names
    assert "ix_workspace_literature_workspace_core_created" in index_names
    assert "ix_workspace_literature_workspace_source_created" in index_names


def test_workspace_literature_core_columns_are_non_nullable() -> None:
    columns = WorkspaceLiterature.__table__.columns
    assert columns["workspace_id"].nullable is False
    assert columns["title"].nullable is False
    assert columns["authors"].nullable is False
    assert columns["source"].nullable is False
    assert columns["is_core"].nullable is False
