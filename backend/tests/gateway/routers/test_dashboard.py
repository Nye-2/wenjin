"""Tests for dashboard router.

This module tests the dashboard endpoint including:
- Dashboard overview with module statuses
- Recent artifacts listing
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers.auth import get_current_user


def create_mock_user(user_id: str = "user-1"):
    user = MagicMock()
    user.id = user_id
    return user


def create_workspace(user_id: str = "user-1"):
    workspace = MagicMock()
    workspace.id = "ws-1"
    workspace.user_id = user_id
    workspace.type = MagicMock(value="thesis")
    return workspace


def create_test_app(user, workspace_service, dashboard_service):
    from src.gateway.routers import workspaces

    app = FastAPI()

    async def override_get_current_user():
        return user

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_dashboard_service():
        return dashboard_service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
    app.dependency_overrides[workspaces.get_dashboard_service] = override_get_dashboard_service
    app.include_router(workspaces.router)
    return TestClient(app)


def test_dashboard_returns_module_statuses():
    ws_svc = AsyncMock()
    ws_svc.get = AsyncMock(return_value=create_workspace())

    dashboard_svc = AsyncMock()
    dashboard_svc.get_dashboard.return_value = {
        "modules": [
            {"id": "deep_research", "status": "not_started", "summary": {}},
            {"id": "literature", "status": "not_started", "summary": {"total": 0, "core": 0}},
            {"id": "opening_research", "status": "not_started", "summary": {}},
            {"id": "thesis_writing", "status": "not_started", "summary": {"outline_done": False}},
            {"id": "figure_generation", "status": "not_started", "summary": {"count": 0}},
            {"id": "compile_export", "status": "not_started", "summary": {}},
        ],
        "recent_artifacts": [],
    }

    client = create_test_app(create_mock_user(), ws_svc, dashboard_svc)
    resp = client.get("/workspaces/ws-1/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["modules"]) == 6
    assert data["modules"][0]["id"] == "deep_research"
    assert data["recent_artifacts"] == []


def test_dashboard_returns_recent_artifacts():
    ws_svc = AsyncMock()
    ws_svc.get = AsyncMock(return_value=create_workspace())

    dashboard_svc = AsyncMock()
    dashboard_svc.get_dashboard.return_value = {
        "modules": [
            {"id": "deep_research", "status": "completed", "summary": {}},
            {"id": "literature", "status": "in_progress", "summary": {"total": 10, "core": 3}},
            {"id": "opening_research", "status": "not_started", "summary": {}},
            {"id": "thesis_writing", "status": "not_started", "summary": {"outline_done": False}},
            {"id": "figure_generation", "status": "not_started", "summary": {"count": 0}},
            {"id": "compile_export", "status": "not_started", "summary": {}},
        ],
        "recent_artifacts": [
            {
                "id": "art-1",
                "type": "research_idea",
                "title": "Test Research Idea",
                "created_at": "2024-01-15T10:00:00+00:00",
            },
            {
                "id": "art-2",
                "type": "methodology",
                "title": "Test Methodology",
                "created_at": "2024-01-14T10:00:00+00:00",
            },
        ],
    }

    client = create_test_app(create_mock_user(), ws_svc, dashboard_svc)
    resp = client.get("/workspaces/ws-1/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["recent_artifacts"]) == 2
    assert data["recent_artifacts"][0]["id"] == "art-1"
    assert data["recent_artifacts"][0]["type"] == "research_idea"


def test_dashboard_returns_404_for_nonexistent_workspace():
    ws_svc = AsyncMock()
    ws_svc.get = AsyncMock(return_value=None)

    dashboard_svc = AsyncMock()

    client = create_test_app(create_mock_user(), ws_svc, dashboard_svc)
    resp = client.get("/workspaces/nonexistent/dashboard")
    assert resp.status_code == 404
