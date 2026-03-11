"""Tests for thesis API endpoints."""

import pytest
from unittest.mock import patch, MagicMock

# We'll test the models and router structure without full app setup


def test_thesis_generate_request_model():
    """Test ThesisGenerateRequest model."""
    from src.thesis.api import ThesisGenerateRequest

    request = ThesisGenerateRequest(
        workspace_id="ws-001",
        paper_title="Test Thesis",
        abstract_content="Abstract content",
        framework_json={"sections": []},
    )
    assert request.workspace_id == "ws-001"
    assert request.paper_title == "Test Thesis"


def test_thesis_status_response_model():
    """Test ThesisStatusResponse model."""
    from src.thesis.api import ThesisStatusResponse

    response = ThesisStatusResponse(
        task_id="task-001",
        status="running",
        progress=0.5,
    )
    assert response.task_id == "task-001"
    assert response.status == "running"
    assert response.progress == 0.5


def test_thesis_task_storage():
    """Test thesis task storage functions."""
    from src.thesis.api import get_thesis_task_status, _thesis_tasks

    # Clear and add a task
    _thesis_tasks.clear()
    _thesis_tasks["test-task"] = {
        "task_id": "test-task",
        "status": "completed",
        "progress": 1.0,
    }

    task = get_thesis_task_status("test-task")
    assert task is not None
    assert task["status"] == "completed"

    # Non-existent task
    assert get_thesis_task_status("non-existent") is None

    # Clean up
    _thesis_tasks.clear()
