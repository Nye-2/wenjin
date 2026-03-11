"""Tests for WorkspaceType enum."""

import pytest
from src.database.models.workspace import WorkspaceType


def test_workspace_type_has_undergraduate_thesis():
    """Test that UNDERGRADUATE_THESIS type exists."""
    assert hasattr(WorkspaceType, "UNDERGRADUATE_THESIS")
    assert WorkspaceType.UNDERGRADUATE_THESIS == "undergraduate_thesis"


def test_workspace_type_values():
    """Test all workspace type values."""
    expected = {
        "sci",
        "thesis",
        "proposal",
        "grant",
        "literature_review",
        "undergraduate_thesis",
    }
    actual = {t.value for t in WorkspaceType}
    assert actual == expected
