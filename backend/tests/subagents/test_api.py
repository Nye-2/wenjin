"""Tests for subagent API routes."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import subagents
from src.api.subagents import get_manager, router
from src.gateway.auth_dependencies import get_current_user
from src.subagents.models import SubagentResult, SubagentStatus


@pytest.fixture
def app():
    """Create FastAPI app with subagent router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_manager():
    """Create mock manager."""
    manager = MagicMock()
    manager._config = MagicMock()
    manager._llm = object()
    manager._config.max_turns_limit = 50
    manager._config.max_timeout = 3600
    manager.spawn = AsyncMock(return_value="task-123")
    manager.get_status = AsyncMock(return_value=SubagentStatus.COMPLETED)
    manager.get_result = AsyncMock(return_value=SubagentResult(
        task_id="task-123",
        status=SubagentStatus.COMPLETED,
        output="Done",
        error=None,
        turns_used=5,
        duration_seconds=10.5,
    ))
    manager.cancel = AsyncMock(return_value=True)
    manager.check_thread_access = AsyncMock(return_value=True)
    manager.subscribe_events = MagicMock(return_value=iter(()))
    return manager


@pytest.fixture(autouse=True)
def override_auth(app):
    """Subagent routes are protected and require an authenticated user."""
    user = MagicMock()
    user.id = "user-123"
    chat_thread_service = MagicMock()
    chat_thread_service.get_thread = AsyncMock(
        return_value=MagicMock(workspace_id="ws-1")
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[subagents.get_chat_thread_service] = lambda: chat_thread_service
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(subagents.get_chat_thread_service, None)


class TestSpawnEndpoint:
    def test_spawn_success(self, client, mock_manager, app):
        """Test successful task spawn."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={"prompt": "Test prompt"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        uuid.UUID(data["task_id"])
        task = mock_manager.spawn.await_args.args[0]
        assert task.metadata["user_id"] == "user-123"
        app.dependency_overrides = {}

    def test_spawn_requires_auth(self, app, mock_manager):
        """Anonymous callers should not reach the subagent API."""
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides[get_manager] = lambda: mock_manager

        client = TestClient(app)
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={"prompt": "Test prompt"},
        )

        assert response.status_code == 401


class TestStatusEndpoint:
    def test_get_status_success(self, client, mock_manager, app):
        """Test getting task status."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.get("/subagents/threads/thread-123/tasks/task-123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["result"]["output"] == "Done"
        assert mock_manager.get_status.await_args.kwargs["user_id"] == "user-123"
        app.dependency_overrides = {}

    def test_get_status_not_found(self, client, mock_manager, app):
        """Test getting status for nonexistent task."""
        mock_manager.get_status = AsyncMock(return_value=None)
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.get("/subagents/threads/thread-123/tasks/unknown/status")
        assert response.status_code == 404
        app.dependency_overrides = {}


class TestCancelEndpoint:
    def test_cancel_success(self, client, mock_manager, app):
        """Test successful task cancellation."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.post("/subagents/threads/thread-123/tasks/task-123/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        app.dependency_overrides = {}

    def test_cancel_not_found(self, client, mock_manager, app):
        """Test canceling nonexistent task."""
        mock_manager.cancel = AsyncMock(return_value=False)
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.post("/subagents/threads/thread-123/tasks/unknown/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        app.dependency_overrides = {}


class TestEventsEndpoint:
    def test_events_endpoint_exists(self, client, app, mock_manager):
        """Test that events endpoint exists."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.get("/subagents/events")
        assert response.status_code in [200, 500]
        app.dependency_overrides = {}

    def test_events_endpoint_rejects_foreign_thread(self, client, app, mock_manager):
        """Thread-scoped event subscriptions should enforce ownership."""
        mock_manager.check_thread_access = AsyncMock(return_value=False)
        app.dependency_overrides[get_manager] = lambda: mock_manager

        response = client.get("/subagents/events", params={"thread_id": "thread-123"})

        assert response.status_code == 404
        app.dependency_overrides = {}


class TestSpawnWithSubagentType:
    """Tests for spawn endpoint with subagent_type parameter."""

    class _Tool:
        def __init__(self, name: str):
            self.name = name

    @pytest.fixture
    def mock_manager_with_tools(self, mock_manager):
        """Create mock manager with tools."""
        mock_manager._tools = {
            "semantic_scholar_search": lambda q: f"search: {q}",
            "read_file": lambda p: f"read: {p}",
            "get_paper_section": lambda s: f"section: {s}",
            "get_paper_toc": lambda: "toc",
        }
        return mock_manager

    @pytest.fixture
    def mock_manager_with_tool_list(self, mock_manager):
        """Create mock manager with the default list-based tool shape."""
        mock_manager._tools = [
            self._Tool("semantic_scholar_search"),
            self._Tool("read_file"),
            self._Tool("get_paper_section"),
            self._Tool("get_paper_toc"),
        ]
        return mock_manager

    def test_spawn_with_valid_subagent_type(self, client, mock_manager_with_tools, app):
        """Test spawning with valid subagent_type."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Search for papers",
                "subagent_type": "scout"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        task = mock_manager_with_tools.spawn.await_args.args[0]
        assert task.metadata["system_prompt"]
        assert "semantic_scholar_search" in set(task.tools)
        app.dependency_overrides = {}

    def test_spawn_with_valid_subagent_type_and_list_backed_tools(
        self,
        client,
        mock_manager_with_tool_list,
        app,
    ):
        """List-backed default tool registries should also resolve cleanly."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tool_list
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Search for papers",
                "subagent_type": "scout",
            },
        )
        assert response.status_code == 200
        app.dependency_overrides = {}

    def test_spawn_with_invalid_subagent_type_returns_400(self, client, mock_manager_with_tools, app):
        """Test spawning with invalid subagent_type returns 400."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Search for papers",
                "subagent_type": "researcher"  # Invalid type
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "UnknownSubagentType" in data["detail"]["error"]
        assert "scout" in str(data["detail"]["valid_types"])
        app.dependency_overrides = {}

    def test_spawn_with_tool_override(self, client, mock_manager_with_tools, app):
        """Test spawning with custom tools override."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Search for papers",
                "subagent_type": "scout",
                "tools": ["read_file"]
            }
        )
        assert response.status_code == 200
        app.dependency_overrides = {}

    def test_spawn_with_invalid_tools_returns_400(self, client, mock_manager_with_tools, app):
        """Test spawning with all invalid tools returns 400."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Search for papers",
                "subagent_type": "scout",
                "tools": ["nonexistent_tool"]
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "InvalidTool" in data["detail"]["error"]
        app.dependency_overrides = {}

    def test_spawn_without_subagent_type_backward_compat(self, client, mock_manager_with_tools, app):
        """Test backward compatibility - spawn without subagent_type."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={"prompt": "Test prompt"}
        )
        assert response.status_code == 200
        app.dependency_overrides = {}
