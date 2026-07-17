"""Contract tests for the PostgreSQL-only runtime accounting cutover."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import ForeignKeyConstraint


def _load_migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "107_runtime_accounting.py"
    )
    spec = importlib.util.spec_from_file_location("migration_107", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ScalarResult:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar(self) -> bool:
        return self.value


class _RecordingOp:
    def __init__(self, *, has_development_data: bool) -> None:
        self.connection = SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql"),
            execute=lambda _statement: _ScalarResult(has_development_data),
        )
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_bind(self):  # noqa: ANN201
        return self.connection

    def __getattr__(self, name: str):
        def record(*args: Any, **kwargs: Any) -> None:
            self.calls.append((name, args, kwargs))

        return record


def test_107_rejects_nonempty_development_data_before_ddl() -> None:
    migration = _load_migration()
    recorder = _RecordingOp(has_development_data=True)
    migration.op = recorder

    with pytest.raises(RuntimeError, match="drop/reseed cutover"):
        migration.upgrade()

    assert recorder.calls == []


def test_107_schema_preserves_finance_and_context_invariants() -> None:
    migration = _load_migration()
    recorder = _RecordingOp(has_development_data=False)
    migration.op = recorder

    migration.upgrade()

    assert migration.revision == "107_runtime_accounting"
    assert migration.down_revision == "106_remove_sandbox_pricing_policy"
    added_columns = {
        (args[0], args[1].name)
        for name, args, _kwargs in recorder.calls
        if name == "add_column"
    }
    assert {
        ("users", "thread_consumed_tokens"),
        ("users", "reserved_thread_free_tokens"),
        ("credit_transactions", "idempotency_key"),
    } <= added_columns
    check_constraints = {
        args[0]
        for name, args, _kwargs in recorder.calls
        if name == "create_check_constraint"
    }
    assert {
        "ck_users_thread_token_counters_nonnegative",
        "ck_users_credit_counters_nonnegative",
    } <= check_constraints

    create_table = next(
        args
        for name, args, _kwargs in recorder.calls
        if name == "create_table" and args[0] == "thread_turn_billings"
    )
    foreign_keys = [
        item for item in create_table[1:] if isinstance(item, ForeignKeyConstraint)
    ]
    targets = {
        tuple(element.target_fullname for element in constraint.elements):
        constraint.ondelete
        for constraint in foreign_keys
    }
    assert ("threads.id",) not in targets
    assert targets[("credit_transactions.id",)] == "RESTRICT"
    assert targets[("thread_messages.id",)] == "SET NULL"


def test_107_is_irreversible() -> None:
    migration = _load_migration()
    with pytest.raises(RuntimeError, match="irreversible development cutover"):
        migration.downgrade()
