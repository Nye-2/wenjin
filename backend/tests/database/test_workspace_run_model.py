from src.database.models.subagent_task import SubagentTaskRecord
from src.database.session import Base


def test_legacy_workspace_run_table_removed_from_metadata():
    assert "workspace_run" not in Base.metadata.tables


def test_subagent_task_run_id_is_unconstrained_legacy_metadata_field():
    column = SubagentTaskRecord.__table__.columns["run_id"]

    assert not column.foreign_keys
