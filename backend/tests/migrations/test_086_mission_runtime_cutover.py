"""Contract tests for the irreversible Mission Runtime clean cut."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "086_mission_runtime_cutover.py"
    )
    spec = importlib.util.spec_from_file_location("mission_runtime_cutover_086", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingOp:
    def __init__(self) -> None:
        self.created_tables: list[str] = []
        self.created_indexes: list[str] = []
        self.executed: list[str] = []

    def create_table(self, table_name: str, *args: Any, **kwargs: Any) -> None:
        _ = args, kwargs
        self.created_tables.append(table_name)

    def create_index(self, index_name: str, *args: Any, **kwargs: Any) -> None:
        _ = args, kwargs
        self.created_indexes.append(index_name)

    def execute(self, statement: Any) -> None:
        self.executed.append(str(statement))


def test_migration_revision_and_exact_core_table_set() -> None:
    migration = _load_migration()
    recorder = _RecordingOp()
    migration.op = recorder

    migration.upgrade()

    assert migration.revision == "086_mission_runtime_cutover"
    assert migration.down_revision == "085_single_gpt55_runtime"
    assert recorder.created_tables == [
        "mission_runs",
        "mission_items",
        "mission_review_items",
        "mission_commits",
    ]
    assert "ix_mission_runs_scheduler" in recorder.created_indexes
    assert "uq_mission_runs_thread_foreground" in recorder.created_indexes


def test_migration_drops_execution_review_history_and_operations_stores() -> None:
    migration = _load_migration()
    recorder = _RecordingOp()
    migration.op = recorder
    migration.upgrade()
    sql = "\n".join(recorder.executed)

    for table_name in (
        "subagent_task_records",
        "compute_sessions",
        "execution_events",
        "execution_nodes",
        "review_action_logs",
        "review_items",
        "review_batches",
        "run_history",
        "executions",
        "dataservice_outbox_events",
        "dataservice_idempotency_keys",
        "dataservice_migration_reports",
    ):
        assert f'DROP TABLE IF EXISTS "{table_name}" CASCADE' in sql
    assert "trg_mission_items_immutable" in sql


def test_migration_is_explicitly_irreversible_in_development() -> None:
    migration = _load_migration()
    with pytest.raises(RuntimeError, match="irreversible development clean cut"):
        migration.downgrade()
