"""Round-trip tests for audit_logs table and AuditService."""

from types import SimpleNamespace

import pytest


class _FakeAuditDataServiceClient:
    def __init__(self) -> None:
        self.records: list[SimpleNamespace] = []

    async def create_audit_log(self, command):
        record = SimpleNamespace(
            id=f"audit-{len(self.records) + 1}",
            action=command.action,
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            target_type=command.target_type,
            target_id=command.target_id,
            payload=command.payload,
            ip=command.ip,
            ua=command.ua,
        )
        self.records.insert(0, record)
        return record

    async def query_audit_logs(
        self,
        *,
        workspace_id=None,
        user_id=None,
        since=None,
        limit=100,
    ):
        _ = since
        results = [
            record
            for record in self.records
            if (workspace_id is None or record.workspace_id == workspace_id)
            and (user_id is None or record.user_id == user_id)
        ]
        return results[:limit]


@pytest.mark.asyncio
async def test_log_and_query():
    """Log an event, query by workspace_id, verify returned."""
    from src.services.audit_service import AuditService

    svc = AuditService(dataservice=_FakeAuditDataServiceClient())

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
async def test_query_by_user():
    """Log 2 events for different users, query returns only matching."""
    from src.services.audit_service import AuditService

    svc = AuditService(dataservice=_FakeAuditDataServiceClient())

    await svc.log("action.a", user_id="u-alpha", workspace_id="ws-1")
    await svc.log("action.b", user_id="u-beta", workspace_id="ws-1")

    results = await svc.query(user_id="u-alpha")
    assert len(results) == 1
    assert results[0].user_id == "u-alpha"
    assert results[0].action == "action.a"
