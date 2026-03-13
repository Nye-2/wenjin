"""Integration tests for task flow.

This module tests the complete task API endpoints including:
- Task submission
- Task status retrieval
- Task listing with filters
- Task cancellation
- SSE streaming endpoint
"""

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.gateway.routers.tasks import (
    get_current_user_id,
    get_task_service,
    router as task_router,
)
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
    async def test_submit_and_get_task(self, task_client, test_user: FixtureUser):
        """Test submitting and retrieving a task."""
        client, app = task_client
        mock_task_id = str(uuid.uuid4())

        # Create mock service
        mock_service = AsyncMock()
        mock_service.submit_task = AsyncMock(return_value=mock_task_id)
        mock_service.get_task_status = AsyncMock(return_value={
            "task_id": mock_task_id,
            "task_type": "paper_processing",
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

        # Submit task
        response = await client.post(
            "/api/tasks/",
            json={
                "task_type": "paper_processing",
                "priority": 5,
                "payload": {"query": "machine learning"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        task_id = data["task_id"]

        # Get status
        response = await client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        status = response.json()
        assert status["task_id"] == task_id
        assert status["task_type"] == "paper_processing"
        assert status["status"] in ("pending", "running")

    @pytest.mark.asyncio
    async def test_submit_billable_task_type_is_blocked(self, task_client, test_user: FixtureUser):
        """Billable task types must use feature execution endpoints."""
        client, app = task_client

        mock_service = AsyncMock()

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        response = await client.post(
            "/api/tasks/",
            json={
                "task_type": "deep_research",
                "payload": {"query": "machine learning"},
            },
        )
        assert response.status_code == 400
        assert "credit accounting" in response.json()["detail"]
        mock_service.submit_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_invalid_task_type(self, task_client, test_user: FixtureUser):
        """Test submitting invalid task type."""
        client, app = task_client

        # Create mock service that raises ValueError for invalid task type
        mock_service = AsyncMock()
        mock_service.submit_task = AsyncMock(side_effect=ValueError("Unknown task type: invalid_type"))

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        response = await client.post(
            "/api/tasks/",
            json={
                "task_type": "invalid_type",
                "payload": {},
            },
        )
        assert response.status_code == 400

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
                "task_type": "literature_search",
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
        response = await client.get("/api/tasks/")
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
            "task_type": "deep_research",
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
    async def test_filter_tasks_by_status(self, task_client, test_user: FixtureUser):
        """Test filtering tasks by status."""
        client, app = task_client
        mock_task_id = str(uuid.uuid4())

        # Create mock service
        mock_service = AsyncMock()
        mock_service.list_tasks = AsyncMock(return_value=[
            {
                "task_id": mock_task_id,
                "task_type": "deep_research",
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
        response = await client.get("/api/tasks/?status=pending")
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
                "task_type": "literature_search",
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
        response = await client.get("/api/tasks/?task_type=literature_search")
        assert response.status_code == 200
        data = response.json()
        for task in data["tasks"]:
            assert task["task_type"] == "literature_search"


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
        response = await client.get("/api/tasks/?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert "count" in data

    @pytest.mark.asyncio
    async def test_submit_task_with_default_priority(self, task_client, test_user: FixtureUser):
        """Test submitting task with default priority."""
        client, app = task_client
        mock_task_id = str(uuid.uuid4())

        # Create mock service
        mock_service = AsyncMock()
        mock_service.submit_task = AsyncMock(return_value=mock_task_id)

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        response = await client.post(
            "/api/tasks/",
            json={
                "task_type": "paper_processing",
                "payload": {"query": "test"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        # Verify default priority was used
        mock_service.submit_task.assert_called_once()
        call_kwargs = mock_service.submit_task.call_args.kwargs
        assert call_kwargs["priority"] == 5  # default priority

    @pytest.mark.asyncio
    async def test_submit_task_with_invalid_priority(self, task_client, test_user: FixtureUser):
        """Test submitting task with invalid priority."""
        client, app = task_client

        # Create mock service
        mock_service = AsyncMock()

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        # Priority out of range (should be 1-10)
        response = await client.post(
            "/api/tasks/",
            json={
                "task_type": "deep_research",
                "priority": 15,
                "payload": {"query": "test"},
            },
        )
        # Should fail validation
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_task_missing_payload(self, task_client, test_user: FixtureUser):
        """Test submitting task without payload."""
        client, app = task_client

        # Create mock service
        mock_service = AsyncMock()

        async def override_get_task_service():
            yield mock_service

        app.dependency_overrides[get_task_service] = override_get_task_service

        response = await client.post(
            "/api/tasks/",
            json={
                "task_type": "deep_research",
            },
        )
        # Should fail validation
        assert response.status_code == 422
