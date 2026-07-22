"""Contract tests for the subagent progress SSOT cutover."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "109_subagent_progress_ssot.py"
    )
    spec = importlib.util.spec_from_file_location("migration_109", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_removes_both_duplicate_snapshot_projections(monkeypatch) -> None:
    migration = _load_migration()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert migration.revision == "109_subagent_progress_ssot"
    assert migration.down_revision == "108_remove_workspace_discipline"
    assert len(statements) == 1
    normalized = " ".join(statements[0].split())
    assert "snapshot_json - 'subagent_summary' - 'team_summary'" in normalized
    assert "snapshot_json ? 'subagent_summary'" in normalized
    assert "snapshot_json ? 'team_summary'" in normalized


def test_migration_is_irreversible() -> None:
    with pytest.raises(RuntimeError, match="irreversible Mission projection SSOT"):
        _load_migration().downgrade()
