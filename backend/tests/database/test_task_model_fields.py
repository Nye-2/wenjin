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
