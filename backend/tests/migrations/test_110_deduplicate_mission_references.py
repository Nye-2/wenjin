from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "110_deduplicate_mission_references.py"
    )
    spec = importlib.util.spec_from_file_location("migration_110", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_recomputes_evidence_count_from_unique_reference_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert migration.revision == "110_deduplicate_mission_references"
    assert migration.down_revision == "109_subagent_progress_ssot"
    assert len(statements) == 1
    statement = " ".join(statements[0].split())
    assert "UPDATE mission_runs AS mission" in statement
    assert "COUNT( DISTINCT COALESCE" in statement
    assert "payload_json ->> 'reference_id'" in statement


def test_downgrade_is_irreversible() -> None:
    migration = _migration()
    with pytest.raises(RuntimeError, match="irreversible"):
        migration.downgrade()
