"""Contract tests for the workspace capability override clean cut."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "094_workspace_override_cleanup.py"
    )
    spec = importlib.util.spec_from_file_location("migration_094", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_drops_workspace_override_column(monkeypatch) -> None:
    migration = _load_migration()
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table, column: calls.append((table, column)),
    )

    assert migration.revision == "094_workspace_override_cleanup"
    assert migration.down_revision == "093_mission_billing_cutover"
    migration.upgrade()
    assert calls == [("workspace_settings", "capability" + "_overrides")]


def test_migration_is_irreversible_clean_cut() -> None:
    migration = _load_migration()

    try:
        migration.downgrade()
    except RuntimeError as exc:
        assert "irreversible development cutover" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("094 downgrade must fail closed")
