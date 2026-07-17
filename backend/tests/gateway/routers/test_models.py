"""Tests for models discovery router."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dataservice_client.contracts.model_catalog import ModelCatalogPayload
from src.gateway.routers import models as models_router
from src.models.capability_profile import (
    GenerationAPI,
    unverified_capability_assessment,
)
from tests.models.capability_fixtures import verified_capability_assessment


def _model_payload(**overrides: Any) -> ModelCatalogPayload:
    verified = bool(overrides.pop("_verified", True))
    data = {
        "id": "row-1",
        "model_id": "gpt-5.6-sol",
        "display_name": "GPT-5.6 Sol",
        "generation_api": "chat_completions",
        "provider_name": "OpenAI",
        "category": "llm",
        "model_name": "gpt-5.6-sol",
        "base_url": "https://api.nainai.love/v1",
        "api_key_redacted": "sk-****abcd",
        "enabled": True,
        "is_default": True,
        "max_tokens": 8192,
    }
    data.update(overrides)
    if verified and data["model_id"] == "gpt-5.6-sol":
        assessment = verified_capability_assessment("gpt-5.6-sol")
    else:
        generation_api = GenerationAPI(data["generation_api"]) if data.get("generation_api") else None
        assessment = unverified_capability_assessment(
            model_id=data["model_id"],
            model_name=data["model_name"],
            base_url=data["base_url"],
            generation_api=generation_api,
        )
    data.update(
        capability_profile=assessment.profile,
        capability_probe=assessment.evidence,
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
    )
    return ModelCatalogPayload.model_validate(data)


class _FakeModelCatalogService:
    def __init__(self) -> None:
        self.seen_purposes: list[str] = []

    async def list_public_models(self, *, purpose: str):
        self.seen_purposes.append(purpose)
        if purpose == "image":
            return [
                _model_payload(
                    model_id="image-model",
                    model_name="image-model",
                    display_name="Image Model",
                    category="image",
                    generation_api=None,
                    _verified=False,
                )
            ]
        return [
            _model_payload(model_id="gpt-5.6-sol", is_default=True),
            _model_payload(
                model_id="qwen-max",
                model_name="qwen-max",
                display_name="Qwen Max",
                base_url="https://api.example.com/v1",
                is_default=False,
                _verified=False,
            ),
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
    assert [model["name"] for model in payload["models"]] == ["gpt-5.6-sol", "qwen-max"]
    assert payload["models"][0]["is_default"] is True
    assert payload["models"][0]["strict_tool_calls"] is True
    assert payload["models"][0]["reasoning_efforts"] == [
        "low",
        "medium",
        "high",
        "xhigh",
    ]
    assert payload["models"][0]["native_web_search"] is True
    assert payload["models"][0]["category"] == "llm"
    assert payload["models"][0]["provider"] == "OpenAI"
    assert service.seen_purposes == ["chat"]


def test_get_model_by_id() -> None:
    client = _create_client(_FakeModelCatalogService())

    response = client.get("/models/qwen-max")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "qwen-max"
    assert payload["display_name"] == "Qwen Max"
    assert payload["strict_tool_calls"] is False


def test_list_models_passes_purpose_filter() -> None:
    service = _FakeModelCatalogService()
    client = _create_client(service)

    response = client.get("/models?purpose=image")

    assert response.status_code == 200
    payload = response.json()
    assert payload["models"][0]["category"] == "image"
    assert service.seen_purposes == ["image"]
