"""Compute session model contract tests."""

from src.database.models.compute_session import ComputeSessionRecord


def test_compute_session_has_execution_session_unique_index() -> None:
    index_names = {idx.name for idx in ComputeSessionRecord.__table__.indexes}

    assert "ix_compute_sessions_execution_session" in index_names
    execution_index = next(
        idx
        for idx in ComputeSessionRecord.__table__.indexes
        if idx.name == "ix_compute_sessions_execution_session"
    )
    assert execution_index.unique is True


def test_compute_session_has_user_workspace_updated_index() -> None:
    index_names = {idx.name for idx in ComputeSessionRecord.__table__.indexes}

    assert "ix_compute_sessions_user_workspace_updated" in index_names

