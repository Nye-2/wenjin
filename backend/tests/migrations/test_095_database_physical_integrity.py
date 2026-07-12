"""Contract tests for the database physical-integrity cutover."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _load_migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "095_database_physical_integrity.py"
    )
    spec = importlib.util.spec_from_file_location("migration_095", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_covers_foreign_keys_and_removes_duplicate_indexes(monkeypatch) -> None:
    migration = _load_migration()
    created: list[tuple[str, str, tuple[str, ...], dict[str, Any]]] = []
    dropped: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda name, table, columns, **kwargs: created.append(
            (name, table, tuple(columns), kwargs)
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda name, *, table_name=None: dropped.append((name, table_name)),
    )

    migration.upgrade()

    assert migration.revision == "095_database_physical_integrity"
    assert migration.down_revision == "094_workspace_override_cleanup"
    assert len(created) == 33
    assert len({name for name, _table, _columns, _kwargs in created}) == 33
    assert all(len(columns) == 1 for _name, _table, columns, _kwargs in created)
    assert sum("postgresql_where" in kwargs for _name, _table, _columns, kwargs in created) == 23
    assert dropped == [
        ("ix_model_catalog_entries_model_id", "model_catalog_entries"),
        ("ix_pricing_policies_policy_key", "pricing_policies"),
        ("ix_thread_messages_thread_sequence", "thread_messages"),
        ("ix_users_email", "users"),
    ]


def test_migration_is_irreversible_clean_cut() -> None:
    migration = _load_migration()

    try:
        migration.downgrade()
    except RuntimeError as exc:
        assert "irreversible development cutover" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("095 downgrade must fail closed")
