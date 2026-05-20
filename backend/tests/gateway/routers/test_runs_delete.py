"""DELETE /runs/{id} removes canonical runtime run records."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import runs
from src.runtime.runs import DisconnectMode, RunRecord, RunStatus


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(runs.router)
    fake_user = MagicMock(id="user-1")
    app.dependency_overrides[runs.get_current_user] = lambda: fake_user
    return TestClient(app)


def _run_record(run_id: str) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        thread_id="thread-1",
        assistant_id=None,
        status=RunStatus.running,
        on_disconnect=DisconnectMode.continue_,
        metadata={"_owner_id": "user-1"},
    )


def test_delete_run_calls_run_manager_cleanup(client):
    """DELETE /runs/{id} should remove the run manager record."""
    manager = MagicMock()
    manager.get_or_load = AsyncMock(return_value=_run_record("run-x"))
    manager.cleanup = AsyncMock()
    thread_service = MagicMock()
    client.app.dependency_overrides[runs.get_run_manager] = lambda: manager
    client.app.dependency_overrides[runs.get_thread_service] = lambda: thread_service

    r = client.delete("/runs/run-x")
    assert r.status_code == 204
    manager.cleanup.assert_awaited_once_with(
        "run-x",
        delay=0,
        remove_persistent=True,
    )


def test_delete_run_returns_404_for_unknown_id(client):
    """Deleting an unknown run now follows canonical run-manager ownership semantics."""
    manager = MagicMock()
    manager.get_or_load = AsyncMock(return_value=None)
    manager.cleanup = AsyncMock()
    client.app.dependency_overrides[runs.get_run_manager] = lambda: manager
    client.app.dependency_overrides[runs.get_thread_service] = lambda: MagicMock()

    r = client.delete("/runs/never-existed")
    assert r.status_code == 404
    manager.cleanup.assert_not_awaited()


def test_delete_run_requires_auth():
    """Without auth override, the endpoint must reject unauthenticated callers."""
    app = FastAPI()
    app.include_router(runs.router)
    # No dependency override — get_current_user will require a real token.
    unauthenticated_client = TestClient(app, raise_server_exceptions=False)
    r = unauthenticated_client.delete("/runs/run-x")
    # 401 or 403 depending on the auth middleware; anything but 204.
    assert r.status_code in (401, 403, 422)
