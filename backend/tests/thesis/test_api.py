"""Tests for thesis API endpoints."""

import pytest

from src.thesis.api import (
    ThesisGenerateRequest,
    ThesisStatusResponse,
    ThesisPreviewResponse,
)
from src.thesis.task_storage import (
    ThesisTask,
    InMemoryTaskStorage,
    set_storage,
    get_storage,
)


# Use isolated storage for tests
@pytest.fixture(autouse=True)
def isolated_storage():
    """Use isolated storage for each test."""
    storage = InMemoryTaskStorage()
    set_storage(storage)
    yield storage
    set_storage(None)  # Reset after test


class TestThesisGenerateRequest:
    """Tests for ThesisGenerateRequest model."""

    def test_valid_request(self):
        """Test valid request creation."""
        request = ThesisGenerateRequest(
            workspace_id="ws-001",
            paper_title="Test Thesis",
            abstract_content="Abstract content",
            framework_json={"sections": []},
        )
        assert request.workspace_id == "ws-001"
        assert request.paper_title == "Test Thesis"
        assert request.enable_search is True
        assert request.enable_images is True

    def test_custom_options(self):
        """Test request with custom options."""
        request = ThesisGenerateRequest(
            workspace_id="ws-002",
            paper_title="  Custom Title  ",  # Test whitespace trimming
            abstract_content="Abstract",
            framework_json={"sections": ["intro", "method"]},
            discipline="物理学",
            enable_search=False,
        )
        assert request.paper_title == "Custom Title"
        assert request.discipline == "物理学"
        assert request.enable_search is False

    def test_empty_title_validation(self):
        """Test that empty title raises validation error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            ThesisGenerateRequest(
                workspace_id="ws-001",
                paper_title="   ",  # Whitespace only
                abstract_content="Abstract",
                framework_json={},
            )


class TestThesisStatusResponse:
    """Tests for ThesisStatusResponse model."""

    def test_response_creation(self):
        """Test response creation."""
        response = ThesisStatusResponse(
            task_id="task-001",
            status="running",
            progress=0.5,
        )
        assert response.task_id == "task-001"
        assert response.status == "running"
        assert response.progress == 0.5
        assert response.current_phase is None

    def test_response_with_all_fields(self):
        """Test response with all fields."""
        response = ThesisStatusResponse(
            task_id="task-002",
            status="completed",
            progress=1.0,
            current_phase="compile",
            message="Thesis generated successfully",
            pdf_path="/output/thesis.pdf",
        )
        assert response.status == "completed"
        assert response.pdf_path == "/output/thesis.pdf"


class TestTaskStorage:
    """Tests for task storage."""

    def test_create_and_get_task(self, isolated_storage):
        """Test creating and retrieving a task."""
        task = ThesisTask(
            task_id="test-task-1",
            workspace_id="ws-001",
            paper_title="Test Thesis",
        )
        isolated_storage.create_task(task)

        retrieved = isolated_storage.get_task("test-task-1")
        assert retrieved is not None
        assert retrieved.task_id == "test-task-1"
        assert retrieved.workspace_id == "ws-001"

    def test_update_task(self, isolated_storage):
        """Test updating a task."""
        task = ThesisTask(
            task_id="test-task-2",
            workspace_id="ws-001",
            paper_title="Test Thesis",
        )
        isolated_storage.create_task(task)

        updated = isolated_storage.update_task("test-task-2", {
            "status": "running",
            "progress": 0.3,
            "current_phase": "writing",
        })
        assert updated is not None
        assert updated.status == "running"
        assert updated.progress == 0.3

    def test_get_nonexistent_task(self, isolated_storage):
        """Test getting a task that doesn't exist."""
        assert isolated_storage.get_task("nonexistent") is None

    def test_delete_task(self, isolated_storage):
        """Test deleting a task."""
        task = ThesisTask(
            task_id="test-task-3",
            workspace_id="ws-001",
            paper_title="Test Thesis",
        )
        isolated_storage.create_task(task)

        assert isolated_storage.delete_task("test-task-3") is True
        assert isolated_storage.get_task("test-task-3") is None
        assert isolated_storage.delete_task("test-task-3") is False  # Already deleted

    def test_list_tasks_with_filter(self, isolated_storage):
        """Test listing tasks filtered by workspace."""
        for i in range(3):
            task = ThesisTask(
                task_id=f"task-{i}",
                workspace_id=f"ws-{i % 2}",  # ws-0, ws-1, ws-0
                paper_title=f"Thesis {i}",
            )
            isolated_storage.create_task(task)

        ws0_tasks = isolated_storage.list_tasks(workspace_id="ws-0")
        assert len(ws0_tasks) == 2

        ws1_tasks = isolated_storage.list_tasks(workspace_id="ws-1")
        assert len(ws1_tasks) == 1

    def test_cleanup_old_tasks(self, isolated_storage):
        """Test cleaning up old tasks."""
        from datetime import datetime, timedelta, UTC

        # Create old completed task
        old_task = ThesisTask(
            task_id="old-task",
            workspace_id="ws-001",
            paper_title="Old Thesis",
            status="completed",
        )
        old_task.created_at = datetime.now(UTC) - timedelta(hours=48)
        isolated_storage.create_task(old_task)

        # Create new task
        new_task = ThesisTask(
            task_id="new-task",
            workspace_id="ws-001",
            paper_title="New Thesis",
            status="pending",
        )
        isolated_storage.create_task(new_task)

        cleaned = isolated_storage.cleanup_old_tasks(max_age_hours=24)
        assert cleaned == 1
        assert isolated_storage.get_task("old-task") is None
        assert isolated_storage.get_task("new-task") is not None
