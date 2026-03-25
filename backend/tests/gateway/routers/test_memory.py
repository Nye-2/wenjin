"""Tests for memory router."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.routers import memory


def _create_client(user_id: str = "user-1") -> TestClient:
    app = FastAPI()

    async def override_get_current_user():
        user = MagicMock()
        user.id = user_id
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.include_router(memory.router)
    return TestClient(app)


def test_get_memory_returns_formatted_context_and_items():
    client = _create_client()

    with patch(
        "src.gateway.routers.memory.load_user_memory",
        AsyncMock(
            return_value=[
                {
                    "category": "preference",
                    "content": "偏好 IEEE",
                    "confidence": 0.9,
                    "workspace_context": "ws-1",
                }
            ]
        ),
    ), patch(
        "src.gateway.routers.memory.build_memory_context",
        AsyncMock(return_value="<academic_memory>\n- 偏好 IEEE\n</academic_memory>"),
    ):
        response = client.get("/memory", params={"workspace_id": "ws-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws-1"
    assert "偏好 IEEE" in payload["formatted_context"]
    assert payload["items"][0]["category"] == "preference"


def test_get_memory_status_includes_runtime_config():
    client = _create_client()

    mock_config = MagicMock()
    mock_config.memory.enabled = True
    mock_config.memory.debounce_seconds = 15
    mock_config.memory.max_facts = 64
    mock_config.memory.fact_confidence_threshold = 0.8
    mock_config.memory.injection_enabled = True
    mock_config.memory.max_injection_tokens = 1200

    with patch(
        "src.gateway.routers.memory.load_user_memory",
        AsyncMock(return_value=[]),
    ), patch(
        "src.gateway.routers.memory.build_memory_context",
        AsyncMock(return_value=""),
    ), patch(
        "src.gateway.routers.memory.get_app_config",
        return_value=mock_config,
        create=True,
    ):
        response = client.get("/memory/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["enabled"] is True
    assert payload["config"]["debounce_seconds"] == 15
    assert payload["config"]["max_facts"] == 64
