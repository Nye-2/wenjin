"""Tests for Alembic version table compatibility guard."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import String, create_engine, inspect, text

from src.database.alembic_version_guard import ensure_alembic_version_column_width


def test_guard_creates_version_table_when_missing() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        action = ensure_alembic_version_column_width(connection)

        assert action == "created"
        columns = inspect(connection).get_columns("alembic_version")
        version_column = next(column for column in columns if column["name"] == "version_num")
        assert getattr(version_column["type"], "length", None) == 191


def test_guard_noop_when_version_table_is_wide_enough() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alembic_version (version_num VARCHAR(255) NOT NULL PRIMARY KEY)"
            )
        )

        action = ensure_alembic_version_column_width(connection)

        assert action == "noop"


def test_guard_alters_column_when_version_table_is_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_connection = MagicMock()

    class _FakeInspector:
        def get_table_names(self) -> list[str]:
            return ["alembic_version"]

        def get_columns(self, _table_name: str) -> list[dict[str, object]]:
            return [{"name": "version_num", "type": String(32)}]

    monkeypatch.setattr(
        "src.database.alembic_version_guard.inspect",
        lambda _connection: _FakeInspector(),
    )

    action = ensure_alembic_version_column_width(fake_connection)

    assert action == "altered"
    fake_connection.execute.assert_called_once()
    executed_sql = str(fake_connection.execute.call_args.args[0])
    assert "ALTER TABLE alembic_version" in executed_sql
    assert "VARCHAR(191)" in executed_sql


def test_guard_rejects_invalid_min_length() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        with pytest.raises(ValueError, match="min_length must be >= 32"):
            ensure_alembic_version_column_width(connection, min_length=31)
