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
    thread_service = MagicMock()
    thread_service.get_thread = AsyncMock(
        return_value=MagicMock(workspace_id="ws-1", model="gpt-4o")
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[subagents.get_thread_service] = lambda: thread_service
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(subagents.get_thread_service, None)


@pytest.fixture(autouse=True)
def override_execution_session_lookup(monkeypatch):
    session = MagicMock(
        id="exec-1",
        user_id="user-123",
        workspace_id="ws-1",
        thread_id="thread-123",
    )
    monkeypatch.setattr(
        subagents,
        "_load_execution_session",
        AsyncMock(return_value=session),
    )
    return session


class TestSpawnEndpoint:
    def test_spawn_success(self, client, mock_manager, app):
        """Test successful task spawn."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                subagents,
                "build_subagent_context_snapshot",
                AsyncMock(return_value="## Inherited Workspace Context\n- workspace_type: sci"),
            )
            response = client.post(
                "/subagents/threads/thread-123/spawn",
                json={"prompt": "Test prompt", "execution_session_id": "exec-1"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        uuid.UUID(data["task_id"])
        task = mock_manager.spawn.await_args.args[0]
        assert task.metadata["user_id"] == "user-123"
        assert "## Inherited Workspace Context" in task.metadata["system_prompt"]
        app.dependency_overrides = {}

    def test_spawn_routes_model_from_thread_and_request(self, client, mock_manager, app):
        """Spawn should route subagent model from request/thread model inputs."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        route_mock = MagicMock(return_value="tool-primary")
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(subagents, "route_subagent_model", route_mock)
            response = client.post(
                "/subagents/threads/thread-123/spawn",
                json={
                    "prompt": "Test prompt",
                    "model_name": "gen-fallback",
                    "execution_session_id": "exec-1",
                },
            )

        assert response.status_code == 200
        route_mock.assert_called_once_with(
            requested_model="gen-fallback",
            thread_model="gpt-4o",
        )
        task = mock_manager.spawn.await_args.args[0]
        assert task.metadata["model_name"] == "tool-primary"
        app.dependency_overrides = {}

    def test_spawn_returns_503_when_no_manager_model_and_routing_fails(self, client, mock_manager, app):
        """Spawn should fail if neither manager llm nor routed model is available."""
        mock_manager._llm = None
        app.dependency_overrides[get_manager] = lambda: mock_manager
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(subagents, "route_subagent_model", MagicMock(return_value=None))
            response = client.post(
                "/subagents/threads/thread-123/spawn",
                json={"prompt": "Test prompt", "execution_session_id": "exec-1"},
            )

        assert response.status_code == 503
        mock_manager.spawn.assert_not_awaited()
        app.dependency_overrides = {}

    def test_spawn_forwards_execution_session_id(self, client, mock_manager, app):
        """Spawn should propagate execution session linkage to subagent metadata."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Test prompt",
                "execution_session_id": "exec-1",
            },
        )

        assert response.status_code == 200
        task = mock_manager.spawn.await_args.args[0]
        assert task.metadata["execution_session_id"] == "exec-1"
        app.dependency_overrides = {}

    def test_spawn_rejects_missing_thread(self, client, mock_manager, app):
        """Spawn should fail fast when the user does not own the thread."""
        thread_service = MagicMock()
        thread_service.get_thread = AsyncMock(return_value=None)
        app.dependency_overrides[get_manager] = lambda: mock_manager
        app.dependency_overrides[subagents.get_thread_service] = lambda: thread_service

        response = client.post(
            "/subagents/threads/thread-404/spawn",
            json={"prompt": "Test prompt", "execution_session_id": "exec-1"},
        )

        assert response.status_code == 404
        mock_manager.spawn.assert_not_awaited()
        app.dependency_overrides = {}

    def test_spawn_uses_subagent_type_limits_when_not_overridden(self, client, mock_manager, app):
        """Per-type max_turns/timeout should be applied when request omits them."""
        app.dependency_overrides[get_manager] = lambda: mock_manager

        class _Resolver:
            def __init__(self, _tools):
                pass

            def resolve_config(self, *_args, **_kwargs):
                return MagicMock(
                    system_prompt="system",
                    tools=["semantic_scholar_search"],
                    model_name=None,
                    max_turns=23,
                    timeout=1234,
                )

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr("src.subagents.academic.AcademicAgentResolver", _Resolver)
            response = client.post(
                "/subagents/threads/thread-123/spawn",
                json={
                    "prompt": "Test prompt",
                    "subagent_type": "scout",
                    "execution_session_id": "exec-1",
                },
            )

        assert response.status_code == 200
        task = mock_manager.spawn.await_args.args[0]
        assert task.max_turns == 23
        assert task.timeout == 1234
        app.dependency_overrides = {}

    def test_spawn_request_limits_override_subagent_type_defaults(self, client, mock_manager, app):
        """Explicit request limits should override per-type default max_turns/timeout."""
        app.dependency_overrides[get_manager] = lambda: mock_manager

        class _Resolver:
            def __init__(self, _tools):
                pass

            def resolve_config(self, *_args, **_kwargs):
                return MagicMock(
                    system_prompt="system",
                    tools=["semantic_scholar_search"],
                    model_name=None,
                    max_turns=23,
                    timeout=1234,
                )

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr("src.subagents.academic.AcademicAgentResolver", _Resolver)
            response = client.post(
                "/subagents/threads/thread-123/spawn",
                json={
                    "prompt": "Test prompt",
                    "subagent_type": "scout",
                    "max_turns": 7,
                    "timeout": 99,
                    "execution_session_id": "exec-1",
                },
            )

        assert response.status_code == 200
        task = mock_manager.spawn.await_args.args[0]
        assert task.max_turns == 7
        assert task.timeout == 99
        app.dependency_overrides = {}

    def test_spawn_rejects_missing_execution_session(self, client, mock_manager, app):
        """Spawn should fail when execution session does not exist."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                subagents,
                "_load_execution_session",
                AsyncMock(return_value=None),
            )
            response = client.post(
                "/subagents/threads/thread-123/spawn",
                json={"prompt": "Test prompt", "execution_session_id": "exec-missing"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Execution session not found"
        mock_manager.spawn.assert_not_awaited()
        app.dependency_overrides = {}

    def test_spawn_rejects_execution_session_thread_mismatch(self, client, mock_manager, app):
        """Spawn should fail when execution session is not bound to the current thread."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(
                subagents,
                "_load_execution_session",
                AsyncMock(
                    return_value=MagicMock(
                        id="exec-1",
                        user_id="user-123",
                        workspace_id="ws-1",
                        thread_id="thread-other",
                    )
                ),
            )
            response = client.post(
                "/subagents/threads/thread-123/spawn",
                json={"prompt": "Test prompt", "execution_session_id": "exec-1"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Execution session not found"
        mock_manager.spawn.assert_not_awaited()
        app.dependency_overrides = {}

    def test_spawn_requires_auth(self, app, mock_manager):
        """Anonymous callers should not reach the subagent API."""
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides[get_manager] = lambda: mock_manager

        client = TestClient(app)
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={"prompt": "Test prompt", "execution_session_id": "exec-1"},
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
                "subagent_type": "scout",
                "execution_session_id": "exec-1",
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
                "execution_session_id": "exec-1",
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
                "subagent_type": "researcher",  # Invalid type
                "execution_session_id": "exec-1",
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
                "tools": ["read_file"],
                "execution_session_id": "exec-1",
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
                "tools": ["nonexistent_tool"],
                "execution_session_id": "exec-1",
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "InvalidTool" in data["detail"]["error"]
        app.dependency_overrides = {}

    def test_spawn_requires_execution_session_id(self, client, mock_manager_with_tools, app):
        """Subagent spawn must be bound to an execution session."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={"prompt": "Test prompt"}
        )
        assert response.status_code == 422
        app.dependency_overrides = {}
