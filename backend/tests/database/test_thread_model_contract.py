"""Thread model contract tests for indexes and data constraints."""

from src.database.models.thread import Thread


def test_thread_has_expected_hot_path_indexes() -> None:
    index_names = {idx.name for idx in Thread.__table__.indexes}
    assert "ix_threads_user_updated" in index_names
    assert "ix_threads_user_workspace_updated" in index_names


def test_thread_has_non_negative_message_count_constraint() -> None:
    constraint_names = {
        constraint.name
        for constraint in Thread.__table__.constraints
        if constraint.name
    }
    assert "ck_threads_message_count_non_negative" in constraint_names
