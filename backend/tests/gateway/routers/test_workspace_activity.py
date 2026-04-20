"""Tests for workspace activity router surface."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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

    async def override_get_current_user():
        return user

    async def override_get_workspace_service():
        return workspace_service

    async def override_get_workspace_activity_service():
        return activity_service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[workspaces.get_workspace_service] = override_get_workspace_service
    app.dependency_overrides[workspaces.get_workspace_activity_service] = (
        override_get_workspace_activity_service
    )
    app.include_router(workspaces.router)
    return TestClient(app)


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


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


def test_workspace_execution_sessions_returns_items():
    workspace_service = AsyncMock()
    workspace_service.get = AsyncMock(return_value=_mock_workspace())

    activity_service = AsyncMock()
    client = _create_client(_mock_user(), workspace_service, activity_service)

    execution = MagicMock()
    execution.id = "exec-1"
    execution.user_id = "user-1"
    execution.workspace_id = "ws-1"
    execution.thread_id = "thread-1"
    execution.workspace_type = "sci"
    execution.feature_id = "framework_outline"
    execution.entry_skill_id = None
    execution.launch_source = "thread"
    execution.launch_message = "开始写全篇论文"
    execution.status = "pending"
    execution.params = {}
    execution.task_ids = ["task-1"]
    execution.primary_task_id = "task-1"
    execution.runtime_snapshot = None
    execution.result_summary = "Queued"
    execution.artifact_ids = []
    execution.next_actions = []
    execution.advisory_code = None
    execution.last_error = None
    execution.created_at = None
    execution.updated_at = None
    execution.started_at = None
    execution.completed_at = None

    with patch(
        "src.gateway.routers.workspaces.ExecutionSessionService.list_workspace_sessions",
        new=AsyncMock(return_value=[execution]),
    ):
        response = client.get("/workspaces/ws-1/executions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == "exec-1"
    assert payload["items"][0]["primary_task_id"] == "task-1"
    assert payload["items"][0]["subagents"] == []
    assert payload["items"][0]["token_usage"] is None
    assert payload["items"][0]["result_payload"] is None


@pytest.mark.asyncio
async def test_execution_enrichment_only_uses_direct_subagent_execution_session_link():
    execution_early = MagicMock()
    execution_early.id = "exec-1"
    execution_early.user_id = "user-1"
    execution_early.workspace_id = "ws-1"
    execution_early.thread_id = "thread-1"
    execution_early.workspace_type = "sci"
    execution_early.feature_id = "framework_outline"
    execution_early.entry_skill_id = None
    execution_early.launch_source = "thread"
    execution_early.launch_message = "Start"
    execution_early.status = "running"
    execution_early.params = {}
    execution_early.task_ids = []
    execution_early.primary_task_id = None
    execution_early.runtime_snapshot = None
    execution_early.result_summary = None
    execution_early.artifact_ids = []
    execution_early.next_actions = []
    execution_early.advisory_code = None
    execution_early.last_error = None
    execution_early.created_at = datetime(2026, 4, 10, 10, 0, tzinfo=UTC)
    execution_early.updated_at = execution_early.created_at
    execution_early.started_at = None
    execution_early.completed_at = datetime(2026, 4, 10, 10, 10, tzinfo=UTC)

    execution_late = MagicMock()
    execution_late.id = "exec-2"
    execution_late.user_id = "user-1"
    execution_late.workspace_id = "ws-1"
    execution_late.thread_id = "thread-1"
    execution_late.workspace_type = "sci"
    execution_late.feature_id = "thesis_full_draft"
    execution_late.entry_skill_id = None
    execution_late.launch_source = "thread"
    execution_late.launch_message = "Continue"
    execution_late.status = "running"
    execution_late.params = {}
    execution_late.task_ids = []
    execution_late.primary_task_id = None
    execution_late.runtime_snapshot = None
    execution_late.result_summary = None
    execution_late.artifact_ids = []
    execution_late.next_actions = []
    execution_late.advisory_code = None
    execution_late.last_error = None
    execution_late.created_at = datetime(2026, 4, 10, 10, 20, tzinfo=UTC)
    execution_late.updated_at = execution_late.created_at
    execution_late.started_at = None
    execution_late.completed_at = None

    directly_linked_subagent = MagicMock()
    directly_linked_subagent.id = "subagent-direct"
    directly_linked_subagent.workspace_id = "ws-1"
    directly_linked_subagent.thread_id = "thread-1"
    directly_linked_subagent.execution_session_id = "exec-2"
    directly_linked_subagent.status = "completed"
    directly_linked_subagent.subagent_type = "scout"
    directly_linked_subagent.output_preview = "Direct session link"
    directly_linked_subagent.error = None
    directly_linked_subagent.task_metadata = {
        "token_usage": {
            "input_tokens": 50,
            "output_tokens": 10,
            "total_tokens": 60,
        },
        "model_name": "gpt-4.1-mini",
    }
    directly_linked_subagent.created_at = datetime(2026, 4, 10, 10, 5, tzinfo=UTC)
    directly_linked_subagent.updated_at = directly_linked_subagent.created_at
    directly_linked_subagent.completed_at = directly_linked_subagent.created_at

    heuristic_subagent = MagicMock()
    heuristic_subagent.id = "subagent-heuristic"
    heuristic_subagent.workspace_id = "ws-1"
    heuristic_subagent.thread_id = "thread-1"
    heuristic_subagent.execution_session_id = "exec-orphan"
    heuristic_subagent.status = "completed"
    heuristic_subagent.subagent_type = "writer"
    heuristic_subagent.output_preview = "Unlinked record"
    heuristic_subagent.error = None
    heuristic_subagent.task_metadata = {}
    heuristic_subagent.created_at = datetime(2026, 4, 10, 10, 6, tzinfo=UTC)
    heuristic_subagent.updated_at = heuristic_subagent.created_at
    heuristic_subagent.completed_at = heuristic_subagent.created_at

    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_ScalarResult([directly_linked_subagent, heuristic_subagent])
    )

    _, subagents_by_execution = await workspaces._load_execution_enrichment(
        db,
        [execution_early, execution_late],
    )

    assert [item["task_id"] for item in subagents_by_execution["exec-2"]] == [
        "subagent-direct"
    ]
    assert subagents_by_execution["exec-2"][0]["token_usage"]["total_tokens"] == 60
    assert subagents_by_execution["exec-2"][0]["model_name"] == "gpt-4.1-mini"
    assert subagents_by_execution["exec-1"] == []
