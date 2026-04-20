"""Execution session model contract tests for query indexes."""

from src.database.models.execution_session import ExecutionSessionRecord


def test_execution_session_has_user_workspace_updated_index() -> None:
    index_names = {idx.name for idx in ExecutionSessionRecord.__table__.indexes}
    assert "ix_execution_sessions_user_workspace_updated" in index_names
