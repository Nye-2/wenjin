"""Tests for execution commit router (Task 2.9)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers.execution_commit import (
    ExecutionCommitService,
    _get_commit_service,
    router,
)

# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


def _make_app(commit_service: ExecutionCommitService) -> TestClient:
    """Create a minimal test app with the commit service overridden."""
    app = FastAPI()

    async def override_commit_service() -> ExecutionCommitService:
        return commit_service

    app.dependency_overrides[_get_commit_service] = override_commit_service
    app.include_router(router)
    return TestClient(app)


def _make_mock_service(**commit_kwargs) -> ExecutionCommitService:
    """Return a mock ExecutionCommitService."""
    svc = MagicMock(spec=ExecutionCommitService)
    svc.commit_outputs = AsyncMock(**commit_kwargs)
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_post_commit_returns_counts():
    """Happy path: service returns counts → 200 with committed dict."""
    expected = {"committed": {"library": 1, "documents": 0, "memory": 0, "decisions": 0, "tasks": 0}}
    svc = _make_mock_service(return_value=expected)
    client = _make_app(svc)

    resp = client.post(
        "/api/executions/exec-1/commit",
        json={"accept_all": True},
    )

    assert resp.status_code == 200
    assert resp.json() == expected
    svc.commit_outputs.assert_called_once_with(
        "exec-1",
        accept_all=True,
        accepted_ids=None,
        idempotency_key=None,
    )


def test_post_commit_400_on_missing_execution():
    """Service raises ValueError → 400 response."""
    svc = _make_mock_service(side_effect=ValueError("execution exec-X not found"))
    client = _make_app(svc)

    resp = client.post(
        "/api/executions/exec-X/commit",
        json={"accept_all": False, "accepted_ids": ["out-1"]},
    )

    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"]


def test_post_commit_passes_idempotency_key_header():
    """Idempotency-Key header is forwarded to the service."""
    expected = {"committed": {"library": 0, "documents": 0, "memory": 1, "decisions": 0, "tasks": 0}}
    svc = _make_mock_service(return_value=expected)
    client = _make_app(svc)

    resp = client.post(
        "/api/executions/exec-2/commit",
        json={"accepted_ids": ["out-mem"]},
        headers={"Idempotency-Key": "idem-key-xyz"},
    )

    assert resp.status_code == 200
    svc.commit_outputs.assert_called_once_with(
        "exec-2",
        accept_all=False,
        accepted_ids=["out-mem"],
        idempotency_key="idem-key-xyz",
    )


def test_post_commit_accepted_ids_only():
    """accepted_ids without accept_all → only those IDs written."""
    expected = {"committed": {"library": 0, "documents": 0, "memory": 0, "decisions": 1, "tasks": 0}}
    svc = _make_mock_service(return_value=expected)
    client = _make_app(svc)

    resp = client.post(
        "/api/executions/exec-3/commit",
        json={"accept_all": False, "accepted_ids": ["out-dec"]},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["committed"]["decisions"] == 1
