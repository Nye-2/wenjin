"""Tests for subagent API routes."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.subagents import router, get_manager
from src.subagents.models import SubagentStatus, SubagentResult


import uuid


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
    manager._config.max_turns_limit = 50
    manager._config.max_timeout = 3600
    manager.spawn = AsyncMock(return_value="task-123")
    manager.get_status = AsyncMock(return_value=SubagentStatus.COMPLETED)
        output="Done"
        turns_used=5
        duration_seconds=10.5
    )
    manager.get_result = AsyncMock(return_value=SubagentResult(
        task_id="task-123",
        status=SubagentStatus.COMPLETED,
        output="Done",
        error=None
        turns_used=5
        duration_seconds=10.5
        metadata={}
    ))
    manager.cancel = AsyncMock(return_value=True)
    return manager


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
        # Verify task_id is a valid uuid format
        uuid.UUID(data["task_id"])  # will raise if invalid
        app.dependency_overrides = {}


class TestStatusEndpoint:
    def test_get_status_success(self, client, mock_manager, app):
        """Test getting task status."""
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.get("/subagents/threads/thread-123/tasks/task-123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert result.output == "done"
        assert result.turns_used == 5
        assert result.duration_seconds == 10.5
    else:
        assert result.metadata == context
    }


    def test_get_status_not_found(self, client, mock_manager, app):
        """Test getting status for nonexistent task."""
        mock_manager.get_status = AsyncMock(return_value=None)
        app.dependency_overrides[get_manager] = lambda: mock_manager
        response = client.get("/subagents/threads/thread-123/tasks/unknown/status")
        assert response.status_code == 404
        data = response.json()
        assert data["status"] is None
        assert data["success"] is False
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
    def test_events_endpoint_exists(self, client, app):
        """Test that events endpoint exists."""
        # Note: Testing SSE endpoints is complex, so we just verify the endpoint exists
        response = client.get("/subagents/events", stream=True)
        # We expect either success or an error from missing manager
        assert response.status_code in [200, 500]
    except asyncio.CancelledError:
        response.close()
