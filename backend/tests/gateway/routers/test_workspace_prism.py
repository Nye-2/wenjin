"""Tests for workspace Prism linkage endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import workspaces
from src.gateway.routers.auth import get_current_user


def _create_user(user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def _create_workspace(user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(
        id="ws-1",
        user_id=user_id,
        name="Workspace 1",
        type=SimpleNamespace(value="thesis"),
    )


def _create_client(*, user_id: str, workspace_owner_id: str) -> TestClient:
    app = FastAPI()

    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_create_workspace(workspace_owner_id))

    async def override_get_current_user():
        return _create_user(user_id)

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_db():
        return object()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
    app.dependency_overrides[workspaces.get_db] = override_get_db
    app.include_router(workspaces.router)
    return TestClient(app)


def test_prism_ensure_returns_linked_project():
    client = _create_client(user_id="user-1", workspace_owner_id="user-1")

    with patch(
        "src.gateway.routers.workspaces.WorkspaceLatexProjectService.ensure_workspace_project",
        new=AsyncMock(return_value=SimpleNamespace(id="latex-1")),
    ) as ensure_project:
        response = client.post("/workspaces/ws-1/prism/ensure")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "latex_project_id": "latex-1",
        "url": "/latex/latex-1",
        "sync_status": "ready",
    }
    ensure_project.assert_awaited_once()


def test_prism_ensure_rejects_non_owner():
    client = _create_client(user_id="user-2", workspace_owner_id="owner-1")
    response = client.post("/workspaces/ws-1/prism/ensure")
    assert response.status_code == 403
