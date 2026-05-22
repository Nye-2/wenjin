"""Tests for workspace activity router surface."""

from datetime import UTC, datetime
from types import SimpleNamespace
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


def _deep_research_capability():
    return SimpleNamespace(
        id="deep_research",
        display_name="深度调研",
        description="深度调研论文主题",
        ui_meta={"icon": "search", "order": 0, "follow_up_prompt": "继续调研"},
        dashboard_meta={"status_kind": "deep_research"},
    )


def _create_dataservice(*, capability=None, executions=None, review_items=None):
    dataservice = MagicMock()
    dataservice.get_catalog_capability = AsyncMock(return_value=capability)
    dataservice.list_executions = AsyncMock(return_value=list(executions or []))
    dataservice.list_review_items = AsyncMock(return_value=list(review_items or []))
    return dataservice


def _create_client(user, workspace_service, activity_service, *, dataservice=None):
    app = FastAPI()
    workspace = getattr(workspace_service.get, "return_value", None)
    workspace_service.has_active_membership = AsyncMock(
        return_value=workspace is not None and str(workspace.user_id) == str(user.id)
    )
    fake_dataservice = dataservice or _create_dataservice(capability=_deep_research_capability())

    async def override_get_current_user():
        return user

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_workspace_activity_service():
        return activity_service

    async def override_get_dataservice_client():
        return fake_dataservice

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
    app.dependency_overrides[workspaces.get_workspace_activity_service] = (
        override_get_workspace_activity_service
    )
    app.dependency_overrides[workspaces.get_dataservice_client] = override_get_dataservice_client

    app.include_router(workspaces.router)
    return TestClient(app)


def test_workspace_activity_returns_items():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace())

    activity_service = AsyncMock()
    activity_service.get_activity.return_value = {
        "items": [
            {
                "id": "thread:thread-1",
                "kind": "thread",
                "workspace_id": "ws-1",
                "occurred_at": "2026-03-20T10:00:00+00:00",
                "title": "Thread session",
                "summary": "Latest reply",
                "status": None,
                "thread_id": "thread-1",
                "task_id": None,
                "artifact_id": None,
                "feature_id": None,
                "subagent_type": None,
                "metadata": {"skill": "deep-research"},
            }
        ],
        "count": 1,
    }

    client = _create_client(_mock_user(), workspace_service, activity_service)
    response = client.get("/workspaces/ws-1/activity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["kind"] == "thread"
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


def test_workspace_executions_returns_items():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace())

    activity_service = AsyncMock()
    execution = MagicMock()
    execution.id = "exec-1"
    execution.user_id = "user-1"
    execution.workspace_id = "ws-1"
    execution.thread_id = "thread-1"
    execution.workspace_type = "sci"
    execution.feature_id = "framework_outline"
    execution.entry_skill_id = None
    execution.display_name = "框架大纲"
    execution.status = "pending"
    execution.execution_type = "capability"
    execution.params = {}
    execution.result = None
    execution.error = None
    execution.graph_structure = None
    execution.node_states = {}
    execution.runtime_state = None
    execution.progress = 0
    execution.message = None
    execution.result_summary = "Queued"
    execution.artifact_ids = []
    execution.next_actions = []
    execution.advisory_code = None
    execution.last_error = None
    execution.parent_execution_id = None
    execution.child_execution_ids = []
    execution.dispatch_mode = None
    execution.worker_task_id = None
    execution.created_at = None
    execution.updated_at = None
    execution.started_at = None
    execution.completed_at = None
    dataservice = _create_dataservice(
        capability=_deep_research_capability(),
        executions=[execution],
        review_items=[],
    )
    client = _create_client(_mock_user(), workspace_service, activity_service, dataservice=dataservice)

    response = client.get("/workspaces/ws-1/executions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == "exec-1"
    assert payload["items"][0]["display_name"] == "框架大纲"
    assert payload["items"][0]["execution_type"] == "capability"
    assert payload["items"][0]["node_states"] == {}
    assert payload["items"][0]["result"] is None
    assert payload["items"][0]["review_items"] == []


def test_workspace_capability_action_resolution_returns_backend_state():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace())

    activity_service = AsyncMock()
    client = _create_client(
        _mock_user(),
        workspace_service,
        activity_service,
        dataservice=_create_dataservice(capability=_deep_research_capability()),
    )

    artifact = MagicMock()
    artifact.id = "artifact-2"
    artifact.type = "framework_outline"
    artifact.title = "LLM Framework"
    artifact.content = {"paper_title": "LLM Planning"}
    artifact.created_at = datetime.now(UTC)

    with (
        patch(
            "src.academic.services.artifact_service.ArtifactService",
        ) as artifact_service_cls,
        patch(
            "src.gateway.routers.workspaces.resolve_feature_action_state",
            return_value={
                "source_artifact_id": "artifact-2",
                "follow_up_prompt": "继续深化框架",
                "route_params": {
                    "topic": "LLM planning",
                    "source_artifact_id": "artifact-2",
                },
                "rerun_params": {
                    "topic": "LLM planning",
                },
                "rerun_unavailable_reason": None,
            },
        ),
    ):
        artifact_service_cls.return_value.list_by_workspace = AsyncMock(
            return_value=[artifact],
        )
        response = client.post(
            "/workspaces/ws-1/capabilities/deep_research/resolve-action",
            json={
                "orchestration_params": {
                    "topic": "LLM planning",
                    "source_artifact_id": "artifact-2",
                },
                "source_artifact_id": None,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_artifact_id"] == "artifact-2"
    assert payload["route_params"]["source_artifact_id"] == "artifact-2"
    assert isinstance(payload["follow_up_prompt"], str)


def test_workspace_capability_action_resolution_returns_404_for_unknown_capability():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace())

    activity_service = AsyncMock()
    client = _create_client(
        _mock_user(),
        workspace_service,
        activity_service,
        dataservice=_create_dataservice(capability=None),
    )

    response = client.post(
        "/workspaces/ws-1/capabilities/unknown_capability/resolve-action",
        json={},
    )

    assert response.status_code == 404
