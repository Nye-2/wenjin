from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.dialects import postgresql, sqlite

from src.database.models.execution import ExecutionRecord
from src.dataservice.domains.execution.repository import (
    _postgres_json_path_text,
    _sqlite_json_path_text,
)


def test_launch_idempotency_key_postgres_query_uses_json_path_operator() -> None:
    stmt = select(ExecutionRecord).where(
        or_(
            _postgres_json_path_text("launch_idempotency_key") == "launch-key-1",
            _postgres_json_path_text("orchestration", "launch_idempotency_key")
            == "launch-key-1",
        )
    )

    compiled = str(stmt.compile(dialect=postgresql.dialect()))

    assert "#>>" in compiled
    assert "executions.params[" not in compiled


def test_launch_idempotency_key_sqlite_query_uses_json_extract() -> None:
    stmt = select(ExecutionRecord).where(
        _sqlite_json_path_text("orchestration", "launch_idempotency_key")
        == "launch-key-1"
    )

    compiled = str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))

    assert "json_extract" in compiled
    assert "$.orchestration.launch_idempotency_key" in compiled
