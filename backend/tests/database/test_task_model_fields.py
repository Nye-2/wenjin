"""TaskRecord must have first-class columns for workspace context."""

from src.database.models.task import TaskRecord


def test_task_record_has_workspace_id_column():
    assert hasattr(TaskRecord, "workspace_id")


def test_task_record_has_feature_id_column():
    assert hasattr(TaskRecord, "feature_id")


def test_task_record_has_thread_id_column():
    assert hasattr(TaskRecord, "thread_id")


def test_task_record_has_action_column():
    assert hasattr(TaskRecord, "action")


def test_task_record_has_progress_range_check_constraint() -> None:
    constraint_names = {
        constraint.name
        for constraint in TaskRecord.__table__.constraints
        if constraint.name
    }
    assert "ck_task_records_progress_range" in constraint_names


def test_task_record_has_dedupe_and_listing_indexes() -> None:
    index_names = {idx.name for idx in TaskRecord.__table__.indexes}
    assert "ix_task_records_user_created" in index_names
    assert "ix_task_records_dedupe_lookup" in index_names
    assert "ix_task_records_active_dedupe_lookup" in index_names
