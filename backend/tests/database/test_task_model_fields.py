"""TaskRecord must have first-class columns for workspace context."""

from src.database.models.task import TaskRecord


def test_task_record_has_workspace_id_column():
    assert hasattr(TaskRecord, "workspace_id")


def test_task_record_has_thread_id_column():
    assert hasattr(TaskRecord, "thread_id")


def test_task_record_has_mission_id_without_feature_execution_columns():
    assert hasattr(TaskRecord, "mission_id")
    assert not hasattr(TaskRecord, "feature_id")
    assert not hasattr(TaskRecord, "action")


def test_task_record_has_progress_range_check_constraint() -> None:
    constraint_names = {
        constraint.name
        for constraint in TaskRecord.__table__.constraints
        if constraint.name
    }
    assert "ck_task_records_progress_range" in constraint_names


def test_task_record_has_auxiliary_task_indexes() -> None:
    index_names = {idx.name for idx in TaskRecord.__table__.indexes}
    assert "ix_task_records_user_created" in index_names
    assert "ix_task_records_mission_id" in index_names
    assert "ix_task_records_status" in index_names
    assert "ix_task_records_dedupe_lookup" not in index_names
    assert "ix_task_records_active_dedupe_lookup" not in index_names
