"""Tests for models discovery router."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dataservice_client.contracts.model_catalog import ModelCatalogPayload
from src.gateway.routers import models as models_router


def _model_payload(**overrides: Any) -> ModelCatalogPayload:
    data = {
        "id": "row-1",
        "model_id": "deepseek-v3",
        "display_name": "DeepSeek V3",
        "provider_protocol": "openai_compatible",
        "provider_name": "QnAIGC",
        "category": "llm",
        "model_name": "deepseek/deepseek-v3",
        "base_url": "https://api.example.com/v1",
        "api_key_redacted": "sk-****abcd",
        "enabled": True,
        "is_default": True,
        "supports_tools": True,
        "supports_reasoning_effort": True,
        "supports_vision": False,
        "max_tokens": 8192,
    }
    data.update(overrides)
    return ModelCatalogPayload.model_validate(data)


class _FakeModelCatalogService:
    def __init__(self) -> None:
        self.seen_purposes: list[str] = []

    async def list_public_models(self, *, purpose: str):
        self.seen_purposes.append(purpose)
        if purpose == "image":
            return [_model_payload(model_id="image-model", display_name="Image Model", category="image")]
        return [
            _model_payload(model_id="deepseek-v3", is_default=True),
            _model_payload(model_id="qwen-max", display_name="Qwen Max", is_default=False, supports_tools=False),
        ]


def _create_client(service: _FakeModelCatalogService) -> TestClient:
    app = FastAPI()
    app.include_router(models_router.router)
    app.dependency_overrides[models_router._service] = lambda: service
    return TestClient(app)


def test_list_models_uses_dataservice_catalog_and_marks_default() -> None:
    service = _FakeModelCatalogService()
    client = _create_client(service)

    response = client.get("/models")

    assert response.status_code == 200
    payload = response.json()
    assert "models" in payload
    assert [model["name"] for model in payload["models"]] == ["deepseek-v3", "qwen-max"]
    assert payload["models"][0]["is_default"] is True
    assert payload["models"][0]["supports_tools"] is True
    assert payload["models"][0]["supports_reasoning_effort"] is True
    assert payload["models"][0]["category"] == "llm"
    assert payload["models"][0]["provider"] == "QnAIGC"
    assert service.seen_purposes == ["chat"]


def test_get_model_by_id() -> None:
    client = _create_client(_FakeModelCatalogService())

    response = client.get("/models/qwen-max")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "qwen-max"
    assert payload["display_name"] == "Qwen Max"
    assert payload["supports_tools"] is False


def test_list_models_passes_purpose_filter() -> None:
    service = _FakeModelCatalogService()
    client = _create_client(service)

    response = client.get("/models?purpose=image")

    assert response.status_code == 200
    payload = response.json()
    assert payload["models"][0]["category"] == "image"
    assert service.seen_purposes == ["image"]
