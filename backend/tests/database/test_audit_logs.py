"""Round-trip tests for audit_logs table and AuditService."""

from contextlib import asynccontextmanager

import pytest

from tests.database.conftest import DbAuditLog


@asynccontextmanager
async def _session_factory(session):
    """Wrap an existing session as a context manager for AuditService."""
    yield session


@pytest.mark.asyncio
async def test_log_and_query(test_session):
    """Log an event, query by workspace_id, verify returned."""
    from src.services.audit_service import AuditService

    svc = AuditService(
        session_factory=lambda: _session_factory(test_session),
        model=DbAuditLog,
    )

    await svc.log(
        "thread.create",
        user_id="u-1",
        workspace_id="ws-1",
        target_type="thread",
        target_id="t-1",
        payload={"title": "Hello"},
    )

    results = await svc.query(workspace_id="ws-1")
    assert len(results) == 1
    assert results[0].action == "thread.create"
    assert results[0].workspace_id == "ws-1"
    assert results[0].user_id == "u-1"
    assert results[0].target_type == "thread"
    assert results[0].target_id == "t-1"


@pytest.mark.asyncio
async def test_query_by_user(test_session):
    """Log 2 events for different users, query returns only matching."""
    from src.services.audit_service import AuditService

    svc = AuditService(
        session_factory=lambda: _session_factory(test_session),
        model=DbAuditLog,
    )

    await svc.log("action.a", user_id="u-alpha", workspace_id="ws-1")
    await svc.log("action.b", user_id="u-beta", workspace_id="ws-1")

    results = await svc.query(user_id="u-alpha")
    assert len(results) == 1
    assert results[0].user_id == "u-alpha"
    assert results[0].action == "action.a"
