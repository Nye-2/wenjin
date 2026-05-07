import pytest

from src.database.models.workspace_run import WorkspaceRunRow
from src.database.models.subagent_task import SubagentTaskRecord


def test_workspace_run_table_exists():
    assert WorkspaceRunRow.__tablename__ == "workspace_run"


def test_subagent_task_has_run_id_fk():
    cols = {c.name for c in SubagentTaskRecord.__table__.columns}
    assert "run_id" in cols
