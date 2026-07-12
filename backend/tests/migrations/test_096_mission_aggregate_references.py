"""Contract tests for Mission aggregate ownership constraints."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "096_mission_aggregate_references.py"
    )
    spec = importlib.util.spec_from_file_location("migration_096", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_enforces_cross_row_mission_ownership(monkeypatch) -> None:
    migration = _load_migration()
    unique_calls: list[tuple[str, str, tuple[str, ...]]] = []
    foreign_calls: list[tuple[object, ...]] = []
    dropped: list[tuple[str, str, str | None]] = []
    monkeypatch.setattr(
        migration.op,
        "create_unique_constraint",
        lambda name, table, columns: unique_calls.append((name, table, tuple(columns))),
    )
    monkeypatch.setattr(
        migration.op,
        "create_foreign_key",
        lambda *args, **kwargs: foreign_calls.append((*args, kwargs)),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda name, table, type_=None: dropped.append((name, table, type_)),
    )

    migration.upgrade()

    assert migration.revision == "096_mission_aggregate_references"
    assert migration.down_revision == "095_database_physical_integrity"
    assert unique_calls == [
        (
            "uq_mission_review_items_mission_item",
            "mission_review_items",
            ("mission_id", "review_item_id"),
        )
    ]
    assert len(foreign_calls) == 2
    assert dropped == [
        ("mission_commits_mission_id_fkey", "mission_commits", "foreignkey"),
        ("mission_commits_review_item_id_fkey", "mission_commits", "foreignkey"),
    ]


def test_migration_is_irreversible_clean_cut() -> None:
    migration = _load_migration()

    try:
        migration.downgrade()
    except RuntimeError as exc:
        assert "irreversible development cutover" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("096 downgrade must fail closed")
