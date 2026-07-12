"""Tests for admin model catalog gateway routes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dataservice_client.contracts.model_catalog import ModelCatalogPayload
from src.dataservice_client.errors import DataServiceClientError
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_admin
from src.gateway.routers import admin_models
from src.models.capability_profile import (
    GenerationAPI,
    unverified_capability_assessment,
)


def _admin() -> AccountAuthSubject:
    return AccountAuthSubject(
        id="admin-1",
        email="admin@example.com",
        name="Admin",
        role="admin",
        is_active=True,
        is_superuser=True,
    )


def _model_payload(**overrides: Any) -> ModelCatalogPayload:
    data = {
        "id": "row-1",
        "model_id": "deepseek-v3",
        "display_name": "DeepSeek V3",
        "generation_api": "chat_completions",
        "provider_name": "QnAIGC",
        "category": "llm",
        "model_name": "deepseek/deepseek-v3",
        "base_url": "https://api.example.com/v1",
        "api_key_redacted": "sk-****abcd",
        "enabled": True,
        "is_default": True,
    }
    data.update(overrides)
    assessment = unverified_capability_assessment(
        model_id=data["model_id"],
        model_name=data["model_name"],
        base_url=data["base_url"],
        generation_api=(GenerationAPI(data["generation_api"]) if data.get("generation_api") else None),
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
        self.created: Any = None
        self.updated: Any = None

    async def list_models(self, *, category: str | None = None, enabled_only: bool = False):
        return [_model_payload()]

    async def create_model(self, data, *, admin_id: str):
        self.created = SimpleNamespace(**data, admin_id=admin_id)
        return _model_payload(model_id=data["model_id"])

    async def update_model(self, model_id: str, data, *, admin_id: str):
        self.updated = (model_id, data, admin_id)
        return _model_payload(model_id=model_id, display_name=data.get("display_name") or "DeepSeek V3")

    async def disable_model(self, model_id: str, *, admin_id: str):
        raise ValueError("Cannot disable the only enabled default model")

    async def set_default_model(self, model_id: str, *, admin_id: str):
        return _model_payload(model_id=model_id, is_default=True)

    async def test_model(self, model_id: str):
        return _model_payload(model_id=model_id, health_status="healthy")


class _FakeDataServiceErrorModelCatalogService(_FakeModelCatalogService):
    async def set_default_model(self, model_id: str, *, admin_id: str):
        _ = model_id, admin_id
        raise DataServiceClientError("model provider rejected default switch", status_code=409)


def _client(
    service: _FakeModelCatalogService,
    *,
    raise_server_exceptions: bool = True,
) -> TestClient:
    app = FastAPI()
    app.include_router(admin_models.router)
    app.dependency_overrides[admin_models._service] = lambda: service
    app.dependency_overrides[get_current_admin] = lambda: _admin()
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_admin_list_models_redacts_key() -> None:
    client = _client(_FakeModelCatalogService())

    response = client.get("/admin/models")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["api_key_redacted"] == "sk-****abcd"
    assert "api_key" not in item


def test_admin_create_passes_admin_id_and_payload() -> None:
    service = _FakeModelCatalogService()
    client = _client(service)

    response = client.post(
        "/admin/models",
        json={
            "model_id": "deepseek-v3",
            "display_name": "DeepSeek V3",
            "model_name": "deepseek/deepseek-v3",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-live-1234abcd",
            "generation_api": "chat_completions",
            "is_default": True,
        },
    )

    assert response.status_code == 200
    assert service.created.admin_id == "admin-1"
    assert service.created.api_key == "sk-live-1234abcd"
    assert response.json()["api_key_redacted"] == "sk-****abcd"


def test_admin_update_passes_admin_id_and_payload() -> None:
    service = _FakeModelCatalogService()
    client = _client(service)

    response = client.patch(
        "/admin/models/deepseek-v3",
        json={"display_name": "DeepSeek V3.1", "api_key": ""},
    )

    assert response.status_code == 200
    model_id, data, admin_id = service.updated
    assert model_id == "deepseek-v3"
    assert data["display_name"] == "DeepSeek V3.1"
    assert data["api_key"] == ""
    assert admin_id == "admin-1"


def test_admin_disable_returns_backend_validation_error() -> None:
    client = _client(_FakeModelCatalogService())

    response = client.post("/admin/models/deepseek-v3/disable")

    assert response.status_code == 400
    assert "default model" in response.json()["detail"]


def test_admin_model_routes_preserve_dataservice_client_status() -> None:
    client = _client(
        _FakeDataServiceErrorModelCatalogService(),
        raise_server_exceptions=False,
    )

    response = client.post("/admin/models/deepseek-v3/set-default")

    assert response.status_code == 409
    assert "default switch" in response.json()["detail"]
