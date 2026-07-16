"""Tests for workspace activity router surface."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import workspaces
from src.gateway.routers.auth import get_current_user
from src.workspace_events import WorkspaceEventStreamUnavailable


def _mock_user(user_id: str = "user-1"):
    user = MagicMock()
    user.id = user_id
    return user


def _mock_workspace(user_id: str = "user-1"):
    workspace = MagicMock()
    workspace.id = "ws-1"
    workspace.user_id = user_id
    workspace.type = MagicMock(value="thesis")
    return workspace


def _create_client(user, workspace_service, activity_service):
    app = FastAPI()
    workspace = getattr(workspace_service.get, "return_value", None)
    workspace_service.has_active_membership = AsyncMock(return_value=workspace is not None and str(workspace.user_id) == str(user.id))

    async def override_get_current_user():
        return user

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_workspace_activity_service():
        return activity_service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
    app.dependency_overrides[workspaces.get_workspace_activity_service] = override_get_workspace_activity_service
    app.include_router(workspaces.router)
    return TestClient(app)


def test_workspace_activity_returns_items():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace())

    activity_service = AsyncMock()
    activity_service.get_activity.return_value = {
        "items": [
            {
                "id": "mission:mission-1",
                "kind": "mission",
                "workspace_id": "ws-1",
                "occurred_at": "2026-03-20T10:00:00+00:00",
                "title": "Literature review",
                "summary": "Map the evidence landscape",
                "status": "running",
                "thread_id": "thread-1",
                "mission_id": "mission-1",
                "mission_policy_id": "sci.v1",
                "metadata": {"active_stage_id": "literature"},
            }
        ],
        "count": 1,
    }

    client = _create_client(_mock_user(), workspace_service, activity_service)
    response = client.get("/workspaces/ws-1/activity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["kind"] == "mission"
    assert payload["items"][0]["thread_id"] == "thread-1"


def test_workspace_activity_enforces_workspace_ownership():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace(user_id="owner-2"))

    activity_service = AsyncMock()
    client = _create_client(_mock_user(user_id="user-1"), workspace_service, activity_service)

    response = client.get("/workspaces/ws-1/activity")

    assert response.status_code == 403


def test_workspace_activity_returns_404_for_missing_workspace():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=None)

    activity_service = AsyncMock()
    client = _create_client(_mock_user(), workspace_service, activity_service)

    response = client.get("/workspaces/ws-1/activity")

    assert response.status_code == 404


def test_workspace_events_stream_requires_owned_workspace():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace())

    activity_service = AsyncMock()
    client = _create_client(_mock_user(), workspace_service, activity_service)

    with patch(
        "src.gateway.routers.workspaces.stream_workspace_events",
        new=AsyncMock(return_value=iter(())),
    ) as mock_stream:
        response = client.get("/workspaces/ws-1/events")

    assert response.status_code == 200
    mock_stream.assert_awaited_once_with("ws-1")


def test_workspace_events_stream_returns_503_when_subscription_fails():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace())

    activity_service = AsyncMock()
    client = _create_client(_mock_user(), workspace_service, activity_service)

    with patch(
        "src.gateway.routers.workspaces.stream_workspace_events",
        new=AsyncMock(side_effect=WorkspaceEventStreamUnavailable("boom")),
    ):
        response = client.get("/workspaces/ws-1/events")

    assert response.status_code == 503
    assert response.json()["detail"] == "Workspace event stream is temporarily unavailable"
