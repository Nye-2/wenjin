"""Tests for deprecated thesis API compatibility routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.handlers.feature_execution_handler import get_feature_execution_handler
from src.gateway.auth_dependencies import get_current_user
from src.gateway.dependencies import get_task_service
from src.thesis.api import router


def _mock_user(user_id: str = "user-1"):
    user = MagicMock()
    user.id = user_id
    return user


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/thesis")

    async def override_user():
        return _mock_user()

    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), app


def _override_task_service(service):
    async def override():
        yield service

    return override


def _override_feature_handler(handler):
    async def override():
        return handler

    return override


def test_generate_thesis_success(client):
    test_client, app = client
    task_service = AsyncMock()
    feature_handler = AsyncMock()

    feature_handler.execute.return_value = {
        "task_id": "task-123",
        "status": "pending",
        "message": "Queued 论文写作",
    }

    app.dependency_overrides[get_task_service] = _override_task_service(task_service)
    app.dependency_overrides[get_feature_execution_handler] = _override_feature_handler(feature_handler)

    response = test_client.post(
        "/api/thesis/generate",
        json={
            "workspace_id": "ws-1",
            "paper_title": "Test Thesis",
            "abstract_content": "Abstract",
            "framework_json": {"chapters": []},
        },
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == "task-123"
    assert response.json()["status"] == "pending"
    feature_handler.execute.assert_awaited_once()


def test_generate_thesis_insufficient_credits_returns_402(client):
    test_client, app = client
    task_service = AsyncMock()
    feature_handler = AsyncMock()
    feature_handler.execute.return_value = {
        "task_id": None,
        "status": "warning",
        "warning": "insufficient_credits",
        "message": "积分不足",
    }

    app.dependency_overrides[get_task_service] = _override_task_service(task_service)
    app.dependency_overrides[get_feature_execution_handler] = _override_feature_handler(feature_handler)

    response = test_client.post(
        "/api/thesis/generate",
        json={
            "workspace_id": "ws-1",
            "paper_title": "Test Thesis",
            "abstract_content": "Abstract",
            "framework_json": {"chapters": []},
        },
    )

    assert response.status_code == 402


def test_get_status_returns_mapped_payload(client):
    test_client, app = client
    task_service = AsyncMock()
    feature_handler = AsyncMock()

    task_service.get_task_status.return_value = {
        "task_id": "task-1",
        "status": "success",
        "progress": 100,
        "message": "Done",
        "error": None,
        "metadata": {"current_phase": "export"},
        "result": {"pdf_path": "/tmp/test.pdf"},
    }

    app.dependency_overrides[get_task_service] = _override_task_service(task_service)
    app.dependency_overrides[get_feature_execution_handler] = _override_feature_handler(feature_handler)

    response = test_client.get("/api/thesis/status/task-1")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["pdf_path"] == "/tmp/test.pdf"


def test_get_preview_returns_preview_payload(client):
    test_client, app = client
    task_service = AsyncMock()
    feature_handler = AsyncMock()

    task_service.get_task_status.return_value = {
        "task_id": "task-1",
        "status": "running",
        "progress": 50,
        "message": "Writing",
        "error": None,
        "metadata": {"sections_completed": 2},
        "result": {"latex_content": "body", "sections_total": 5},
    }

    app.dependency_overrides[get_task_service] = _override_task_service(task_service)
    app.dependency_overrides[get_feature_execution_handler] = _override_feature_handler(feature_handler)

    response = test_client.get("/api/thesis/preview/task-1")

    assert response.status_code == 200
    assert response.json()["latex_content"] == "body"
    assert response.json()["sections_completed"] == 2
    assert response.json()["sections_total"] == 5


def test_list_tasks_filters_by_workspace(client):
    test_client, app = client
    task_service = AsyncMock()
    feature_handler = AsyncMock()

    record_a = SimpleNamespace(
        id="task-a",
        task_type="workspace_feature",
        payload={"workspace_id": "ws-1", "feature_id": "thesis_writing"},
    )
    record_b = SimpleNamespace(
        id="task-b",
        task_type="workspace_feature",
        payload={"workspace_id": "ws-2", "feature_id": "thesis_writing"},
    )

    task_service.list_task_records.return_value = [record_a, record_b]
    task_service.get_task_status.side_effect = [
        {"task_id": "task-a", "status": "pending", "progress": 0, "message": None, "error": None, "metadata": None, "result": None},
    ]

    app.dependency_overrides[get_task_service] = _override_task_service(task_service)
    app.dependency_overrides[get_feature_execution_handler] = _override_feature_handler(feature_handler)

    response = test_client.get("/api/thesis/list", params={"workspace_id": "ws-1"})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["task_id"] == "task-a"
