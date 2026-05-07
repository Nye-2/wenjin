import pytest

from src.database.models.subagent_task import SubagentTaskRecord


def test_subagent_task_has_criticality_column():
    cols = {c.name for c in SubagentTaskRecord.__table__.columns}
    assert "criticality" in cols


def test_default_criticality_is_low():
    col = SubagentTaskRecord.__table__.columns["criticality"]
    assert col.default is not None
    assert col.default.arg == "low"
