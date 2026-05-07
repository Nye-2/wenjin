"""Spec §6.2 B3 — DELETE /runs/{id} soft-deletes a workspace_run row."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import runs


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(runs.router)
    fake_user = MagicMock(id="user-1")
    app.dependency_overrides[runs.get_current_user] = lambda: fake_user
    return TestClient(app)


def test_delete_run_calls_service(client, monkeypatch):
    """DELETE /runs/{id} should call WorkspaceRunService.delete_run with the run id."""
    called = AsyncMock()
    monkeypatch.setattr(
        "src.services.workspace_run_service.WorkspaceRunService.delete_run",
        called,
    )

    # Patch get_db_session to a no-op async context manager that returns a mock session.
    class _FakeSession:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("src.database.session.get_db_session", lambda: _FakeSession())

    r = client.delete("/runs/run-x")
    assert r.status_code == 204
    called.assert_called_once_with("run-x")


def test_delete_run_returns_204_for_unknown_id(client, monkeypatch):
    """Deleting an unknown run is a silent no-op per WorkspaceRunService contract."""
    # Service silently returns None for missing rows — HTTP layer must still 204.
    monkeypatch.setattr(
        "src.services.workspace_run_service.WorkspaceRunService.delete_run",
        AsyncMock(return_value=None),
    )

    class _FakeSession:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("src.database.session.get_db_session", lambda: _FakeSession())

    r = client.delete("/runs/never-existed")
    assert r.status_code == 204


def test_delete_run_requires_auth():
    """Without auth override, the endpoint must reject unauthenticated callers."""
    app = FastAPI()
    app.include_router(runs.router)
    # No dependency override — get_current_user will require a real token.
    unauthenticated_client = TestClient(app, raise_server_exceptions=False)
    r = unauthenticated_client.delete("/runs/run-x")
    # 401 or 403 depending on the auth middleware; anything but 204.
    assert r.status_code in (401, 403, 422)
