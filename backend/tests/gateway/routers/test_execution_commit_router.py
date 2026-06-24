"""Tests for execution commit router (Task 2.9)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import (
    get_current_user,
)
from src.gateway.auth_dependencies import (
    get_dataservice_client as auth_get_dataservice_client,
)
from src.gateway.routers.execution_commit import (
    _get_commit_service,
    router,
)
from src.services.execution_commit_service import (
    ExecutionCommitConcurrencyError,
    ExecutionCommitNotFoundError,
    ExecutionCommitPersistenceError,
    ExecutionCommitService,
)

# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


class _FakeUser:
    id = "user-1"


def _make_app(
    commit_service: ExecutionCommitService,
    *,
    authenticated: bool = True,
    raise_server_exceptions: bool = True,
) -> TestClient:
    """Create a minimal test app with the commit service overridden."""
    app = FastAPI()

    async def override_commit_service() -> ExecutionCommitService:
        return commit_service

    async def override_dataservice():
        yield MagicMock()

    app.dependency_overrides[_get_commit_service] = override_commit_service
    app.dependency_overrides[auth_get_dataservice_client] = override_dataservice
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


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
        output_overrides=None,
        idempotency_key=None,
        actor_user_id="user-1",
    )


def test_post_commit_404_on_missing_execution():
    """Missing executions should use the same hidden/not-found contract as non-owners."""
    svc = _make_mock_service(
        side_effect=ExecutionCommitNotFoundError("execution exec-X not found")
    )
    client = _make_app(svc)

    resp = client.post(
        "/api/executions/exec-X/commit",
        json={"accept_all": False, "accepted_ids": ["out-1"]},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Execution not found"


def test_post_commit_409_on_commit_in_progress():
    """Concurrent commit attempts should return a retryable conflict response."""
    svc = _make_mock_service(
        side_effect=ExecutionCommitConcurrencyError(
            "execution exec-1 commit is already in progress"
        )
    )
    client = _make_app(svc, raise_server_exceptions=False)

    resp = client.post(
        "/api/executions/exec-1/commit",
        json={"accept_all": True},
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Commit already in progress"


def test_post_commit_500_on_commit_state_persistence_failure():
    """Durable commit_state write failures should surface as explicit server errors."""
    svc = _make_mock_service(
        side_effect=ExecutionCommitPersistenceError(
            "commit_state persistence failed for execution exec-1"
        )
    )
    client = _make_app(svc, raise_server_exceptions=False)

    resp = client.post(
        "/api/executions/exec-1/commit",
        json={"accept_all": True},
    )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Commit state persistence failed"


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
        output_overrides=None,
        idempotency_key="idem-key-xyz",
        actor_user_id="user-1",
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


def test_post_commit_passes_output_overrides():
    """Staged frontend edits are forwarded to the commit service."""
    expected = {"committed": {"library": 0, "documents": 1, "memory": 0, "decisions": 0, "tasks": 0}}
    svc = _make_mock_service(return_value=expected)
    client = _make_app(svc)

    resp = client.post(
        "/api/executions/exec-4/commit",
        json={
            "accept_all": True,
            "output_overrides": {
                "out-doc": {"data": {"name": "edited.md"}, "preview": "Edited doc"}
            },
        },
    )

    assert resp.status_code == 200
    svc.commit_outputs.assert_called_once_with(
        "exec-4",
        accept_all=True,
        accepted_ids=None,
        output_overrides={
            "out-doc": {"data": {"name": "edited.md"}, "preview": "Edited doc"}
        },
        idempotency_key=None,
        actor_user_id="user-1",
    )


def test_post_commit_requires_authenticated_user():
    """Commit is a writeback operation and must reject anonymous callers."""
    svc = _make_mock_service(return_value={"committed": {}})
    client = _make_app(svc, authenticated=False)

    resp = client.post(
        "/api/executions/exec-1/commit",
        json={"accept_all": True},
    )

    assert resp.status_code == 401
    svc.commit_outputs.assert_not_called()


def test_post_commit_hides_execution_for_non_owner():
    """A commit rejected by ownership checks is surfaced as not found."""
    svc = _make_mock_service(
        side_effect=ExecutionCommitNotFoundError("execution exec-1 not found")
    )
    client = _make_app(svc)

    resp = client.post(
        "/api/executions/exec-1/commit",
        json={"accept_all": True},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Execution not found"
