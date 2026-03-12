"""Tests for WorkspaceType enum."""

from src.database.models.workspace import WorkspaceType


def test_workspace_type_values():
    """Test all workspace type values."""
    expected = {
        "sci",
        "thesis",
        "proposal",
        "software_copyright",
        "patent",
    }
    actual = {t.value for t in WorkspaceType}
    assert actual == expected
