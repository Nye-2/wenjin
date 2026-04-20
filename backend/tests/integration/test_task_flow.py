"""Integration tests for task status/list/stream/cancel flow."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.gateway.routers.tasks import (
    get_current_user_id,
    get_task_service,
)
from src.gateway.routers.tasks import (
    router as task_router,
)
from src.task.sse import TaskEventStreamUnavailable
from tests.integration.conftest import FixtureUser


@pytest_asyncio.fixture
async def task_client(test_user: FixtureUser, test_user_tokens: dict):
    """Create a test client with task routes and mocked dependencies."""
    app = FastAPI()
    app.include_router(task_router, prefix="/api")

    # Override the user_id dependency
    async def override_get_user_id():
        return str(test_user.id)

    app.dependency_overrides[get_current_user_id] = override_get_user_id

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        ac.headers["Authorization"] = f"Bearer {test_user_tokens['access_token']}"
        yield ac, app


class TestTaskFlow:
    """Tests for complete task flow."""

    @pytest.mark.asyncio
    async def test_get_task(self, task_client, test_user: FixtureUser):
        """Test retrieving a task."""
        client, app = task_client
        mock_task_id = str(uuid.uuid4())

        # Create mock service
        mock_service = AsyncMock()
        mock_service.get_task_status = AsyncMock(return_value={
            "task_id": mock_task_id,
            "task_type": "workspace_feature",
            "status": "pending",
            "progress": 0,
            "message": "Task submitted",
            "result": None,
            "error": None,
            "created_at": "2024-01-01T00:00:00",
            "started_at": None,
            "completed_at": None,
        })

        # Override the task service dependency
        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        # Get status
        response = await client.get(f"/api/tasks/{mock_task_id}")
        assert response.status_code == 200
        status = response.json()
        assert status["task_id"] == mock_task_id
        assert status["task_type"] == "workspace_feature"
        assert status["status"] in ("pending", "running")

    @pytest.mark.asyncio
    async def test_direct_task_submission_route_is_removed_for_workspace_feature(
        self, task_client, test_user: FixtureUser
    ):
        """Raw task creation should no longer be exposed on /api/tasks."""
        client, _app = task_client
        response = await client.post(
            "/api/tasks",
            json={
                "task_type": "workspace_feature",
                "payload": {
                    "workspace_id": "ws-1",
                    "workspace_type": "thesis",
                    "feature_id": "deep_research",
                    "query": "machine learning",
                },
            },
        )
        assert response.status_code == 405
        assert response.json()["detail"] == "Method Not Allowed"

    @pytest.mark.asyncio
    async def test_direct_task_submission_route_is_removed_before_task_type_validation(
        self, task_client, test_user: FixtureUser
    ):
        """Route removal should fail before any task-type validation logic exists."""
        client, _app = task_client
        response = await client.post(
            "/api/tasks",
            json={
                "task_type": "invalid_type",
                "payload": {},
            },
        )
        assert response.status_code == 405
        assert response.json()["detail"] == "Method Not Allowed"

    @pytest.mark.asyncio
    async def test_list_tasks(self, task_client, test_user: FixtureUser):
        """Test listing tasks."""
        client, app = task_client
        mock_task_id = str(uuid.uuid4())

        # Create mock service
        mock_service = AsyncMock()
        mock_service.list_tasks = AsyncMock(return_value=[
            {
                "task_id": mock_task_id,
                "task_type": "workspace_feature",
                "status": "pending",
                "progress": 0,
                "message": "Task submitted",
                "created_at": "2024-01-01T00:00:00",
                "completed_at": None,
            }
        ])

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        # List tasks
        response = await client.get("/api/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert "count" in data
        assert data["count"] >= 1

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, task_client, test_user: FixtureUser):
        """Test getting nonexistent task."""
        client, app = task_client
        fake_id = str(uuid.uuid4())

        # Create mock service that returns None for nonexistent task
        mock_service = AsyncMock()
        mock_service.get_task_status = AsyncMock(return_value=None)

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        response = await client.get(f"/api/tasks/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_task(self, task_client, test_user: FixtureUser):
        """Test cancelling a task."""
        client, app = task_client
        mock_task_id = str(uuid.uuid4())

        # Create mock service
        mock_service = AsyncMock()
        mock_service.submit_task = AsyncMock(return_value=mock_task_id)
        mock_service.cancel_task = AsyncMock(return_value=True)
        mock_service.get_task_status = AsyncMock(return_value={
            "task_id": mock_task_id,
            "task_type": "workspace_feature",
            "status": "cancelled",
            "progress": 0,
            "message": "Cancelled by user",
            "result": None,
            "error": None,
            "created_at": "2024-01-01T00:00:00",
            "started_at": None,
            "completed_at": "2024-01-01T00:00:01",
        })

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        # Cancel task
        response = await client.delete(f"/api/tasks/{mock_task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify cancelled status
        response = await client.get(f"/api/tasks/{mock_task_id}")
        status = response.json()
        assert status["status"] in ("cancelled", "pending", "running")

    @pytest.mark.asyncio
    async def test_task_sse_endpoint_exists(self, task_client, test_user: FixtureUser):
        """Test SSE endpoint exists."""
        client, app = task_client
        fake_id = str(uuid.uuid4())

        # Create mock service that returns None for nonexistent task
        mock_service = AsyncMock()
        mock_service.get_task_status = AsyncMock(return_value=None)

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        response = await client.get(f"/api/tasks/{fake_id}/stream")
        # Should return 404 for nonexistent task
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_task_sse_endpoint_returns_503_when_stream_unavailable(
        self, task_client, test_user: FixtureUser
    ):
        """Task SSE should fail before streaming when Redis subscribe cannot start."""
        client, app = task_client
        fake_id = str(uuid.uuid4())

        mock_service = AsyncMock()
        mock_service.get_task_status = AsyncMock(return_value={
            "task_id": fake_id,
            "task_type": "workspace_feature",
            "status": "running",
            "progress": 10,
            "message": "Running",
            "result": None,
            "error": None,
            "created_at": "2024-01-01T00:00:00",
            "started_at": None,
            "completed_at": None,
        })

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        with patch(
            "src.task.sse.create_task_sse_stream",
            new=AsyncMock(side_effect=TaskEventStreamUnavailable("boom")),
        ):
            response = await client.get(f"/api/tasks/{fake_id}/stream")

        assert response.status_code == 503
        assert response.json()["detail"] == "Task event stream is temporarily unavailable"

    @pytest.mark.asyncio
    async def test_filter_tasks_by_status(self, task_client, test_user: FixtureUser):
        """Test filtering tasks by status."""
        client, app = task_client
        mock_task_id = str(uuid.uuid4())

        # Create mock service
        mock_service = AsyncMock()
        mock_service.list_tasks = AsyncMock(return_value=[
            {
                "task_id": mock_task_id,
                "task_type": "workspace_feature",
                "status": "pending",
                "progress": 0,
                "message": "Task submitted",
                "created_at": "2024-01-01T00:00:00",
                "completed_at": None,
            }
        ])

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        # Filter by pending status
        response = await client.get("/api/tasks?status=pending")
        assert response.status_code == 200
        data = response.json()
        for task in data["tasks"]:
            assert task["status"] == "pending"

    @pytest.mark.asyncio
    async def test_filter_tasks_by_type(self, task_client, test_user: FixtureUser):
        """Test filtering tasks by type."""
        client, app = task_client
        mock_task_id = str(uuid.uuid4())

        # Create mock service
        mock_service = AsyncMock()
        mock_service.list_tasks = AsyncMock(return_value=[
            {
                "task_id": mock_task_id,
                "task_type": "workspace_feature",
                "status": "pending",
                "progress": 0,
                "message": "Task submitted",
                "created_at": "2024-01-01T00:00:00",
                "completed_at": None,
            }
        ])

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        # Filter by task type
        response = await client.get("/api/tasks?task_type=workspace_feature")
        assert response.status_code == 200
        data = response.json()
        for task in data["tasks"]:
            assert task["task_type"] == "workspace_feature"


class TestTaskFlowEdgeCases:
    """Tests for task flow edge cases."""

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self, task_client, test_user: FixtureUser):
        """Test cancelling a nonexistent task."""
        client, app = task_client
        fake_id = str(uuid.uuid4())

        # Create mock service that returns False for nonexistent task
        mock_service = AsyncMock()
        mock_service.cancel_task = AsyncMock(return_value=False)

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        response = await client.delete(f"/api/tasks/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_completed_task_fails(self, task_client, test_user: FixtureUser):
        """Test that cancelling a completed task fails."""
        client, app = task_client
        mock_task_id = str(uuid.uuid4())

        # Create mock service that returns False for completed task
        mock_service = AsyncMock()
        mock_service.cancel_task = AsyncMock(return_value=False)

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        response = await client.delete(f"/api/tasks/{mock_task_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_tasks_with_limit(self, task_client, test_user: FixtureUser):
        """Test listing tasks with limit parameter."""
        client, app = task_client

        # Create mock service
        mock_service = AsyncMock()
        mock_service.list_tasks = AsyncMock(return_value=[])

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        # List tasks with limit
        response = await client.get("/api/tasks?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert "count" in data

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("payload", "label"),
        [
            (
                {
                    "task_type": "paper_processing",
                    "payload": {"query": "test"},
                },
                "legacy raw task type",
            ),
            (
                {
                    "task_type": "workspace_feature",
                    "priority": 15,
                    "payload": {"feature_id": "deep_research", "query": "test"},
                },
                "invalid priority body",
            ),
            (
                {
                    "task_type": "workspace_feature",
                },
                "missing payload body",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_post_tasks_is_removed_regardless_of_request_body(
        self,
        task_client,
        test_user: FixtureUser,
        payload: dict,
        label: str,
    ):
        """Route removal should win over any legacy submit payload variations."""
        client, _app = task_client

        response = await client.post("/api/tasks", json=payload)

        assert response.status_code == 405, label
        assert response.json()["detail"] == "Method Not Allowed"
