"""Tests for legacy LaTeX route workspace redirects."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps.core import get_db
from src.gateway.routers import latex


def _create_client() -> TestClient:
    app = FastAPI()

    async def override_get_current_user():
        return SimpleNamespace(id="user-1")

    async def override_get_db():
        return object()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(latex.router)
    return TestClient(app)


def test_workspace_owned_project_redirects_to_workspace_prism():
    client = _create_client()

    with patch(
        "src.gateway.routers.latex.WorkspacePrismService.resolve_workspace_from_project",
        new=AsyncMock(return_value=("ws-1", SimpleNamespace(id="latex-1"))),
        create=True,
    ):
        response = client.get("/latex/latex-1", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/workspaces/ws-1/prism"
