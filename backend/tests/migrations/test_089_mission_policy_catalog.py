"""Clean-cut migration tests for the Mission policy catalog."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    migration_path = Path(__file__).parents[2] / "alembic" / "versions" / "089_mission_policy_catalog.py"
    spec = spec_from_file_location("mission_policy_catalog_089", migration_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_089_renders_two_table_clean_cut_postgresql_sql() -> None:
    module = _migration_module()
    output = StringIO()
    context = MigrationContext.configure(url="postgresql://", opts={"as_sql": True, "output_buffer": output})
    module.op = Operations(context)
    module.upgrade()
    sql = output.getvalue()

    assert module.down_revision == "088_mission_linked_domains"
    assert "CREATE TABLE mission_policies" in sql
    assert "CREATE TABLE worker_skills" in sql
    assert "content_hash VARCHAR(64) NOT NULL" in sql
    for old_table in (
        "agent_templates",
        "capability_skills",
        "capabilities",
        "capability_seed_revisions",
        "capability_definitions",
    ):
        assert f"DROP TABLE {old_table}" in sql


def test_089_downgrade_is_explicitly_irreversible() -> None:
    with pytest.raises(RuntimeError, match="irreversible development cutover"):
        _migration_module().downgrade()
