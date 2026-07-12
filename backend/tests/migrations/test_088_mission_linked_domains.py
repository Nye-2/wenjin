from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_088_renders_clean_cut_postgresql_offline_sql() -> None:
    migration_path = Path(__file__).parents[2] / "alembic" / "versions" / "088_mission_linked_domains.py"
    spec = spec_from_file_location("mission_linked_domains_088", migration_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    output = StringIO()
    context = MigrationContext.configure(
        url="postgresql://",
        opts={"as_sql": True, "output_buffer": output},
    )
    module.op = Operations(context)
    module.upgrade()
    sql = output.getvalue()

    assert "related_mission_ids" in sql
    assert "source_mission_commit_id" in sql
    assert "mission_review_item_id" in sql
    assert "mission_item_seq BIGINT" in sql
    assert 'DROP TABLE IF EXISTS "executions" CASCADE' in sql
    assert "accepted_ids" not in sql
    assert "CREATE TABLE" not in sql
