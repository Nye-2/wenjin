"""Tests for gateway model catalog service facade."""

from __future__ import annotations

from typing import Any

import pytest

from src.dataservice_client.contracts.model_catalog import (
    ModelCatalogPayload,
    ModelRuntimeConfigPayload,
)
from src.models.capability_profile import (
    GenerationAPI,
    unverified_capability_assessment,
)
from src.services.model_catalog_cache import reset_model_catalog_cache
from src.services.model_catalog_service import ModelCatalogService
from tests.models.capability_fixtures import verified_capability_assessment


def _model_payload(**overrides: Any) -> ModelCatalogPayload:
    data = {
        "id": "row-1",
        "model_id": "deepseek-v3",
        "display_name": "DeepSeek V3",
        "model_name": "deepseek/deepseek-v3",
        "base_url": "https://api.example.com/v1",
        "api_key_redacted": "sk-****abcd",
        "provider_name": "QnAIGC",
        "category": "llm",
        "enabled": True,
        "is_default": True,
        "generation_api": "chat_completions",
    }
    data.update(overrides)
    assessment = unverified_capability_assessment(
        model_id=data["model_id"],
        model_name=data["model_name"],
        base_url=data["base_url"],
        generation_api=GenerationAPI(data["generation_api"]),
    )
    data.update(
        capability_profile=assessment.profile,
        capability_probe=assessment.evidence,
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
    )
    return ModelCatalogPayload.model_validate(data)


def _runtime_payload(**overrides: Any) -> ModelRuntimeConfigPayload:
    data = {
        "model_id": "deepseek-v3",
        "display_name": "DeepSeek V3",
        "provider_name": "QnAIGC",
        "category": "llm",
        "model_name": "deepseek/deepseek-v3",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-live-1234abcd",
        "is_default": True,
        "generation_api": "chat_completions",
        "timeout_seconds": 30,
        "max_retries": 0,
    }
    data.update(overrides)
    assessment = unverified_capability_assessment(
        model_id=data["model_id"],
        model_name=data["model_name"],
        base_url=data["base_url"],
        generation_api=GenerationAPI(data["generation_api"]),
    )
    data.update(
        capability_profile=assessment.profile,
        capability_probe=assessment.evidence,
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
    )
    return ModelRuntimeConfigPayload.model_validate(data)


@pytest.fixture(autouse=True)
def _reset_runtime_cache() -> None:
    reset_model_catalog_cache()
    yield
    reset_model_catalog_cache()


class _FakeDataService:
    def __init__(self) -> None:
        self.created: Any = None
        self.updated: list[tuple[str, Any]] = []
        self.defaults: list[tuple[str, str | None]] = []
        self.health_updates: list[tuple[str, Any]] = []
        self.capability_updates: list[tuple[str, Any]] = []
        self.items = [
            _model_payload(model_id="enabled-model", enabled=True),
            _model_payload(model_id="disabled-model", enabled=False),
        ]
        self.runtime_items = [_runtime_payload()]

    async def list_model_catalog_models(self, *, category: str | None = None, enabled_only: bool = False):
        items = [item for item in self.items if category is None or item.category == category]
        if enabled_only:
            items = [item for item in items if item.enabled]
        return items

    async def list_model_catalog_runtime_models(self, *, category: str | None = None):
        return [item for item in self.runtime_items if category is None or item.category == category]

    async def get_model_catalog_runtime_model(self, model_id: str):
        return next(
            (item for item in self.runtime_items if item.model_id == model_id),
            None,
        )

    async def create_model_catalog_model(self, command):
        self.created = command
        return _model_payload(model_id=command.model_id)

    async def update_model_catalog_model(self, model_id: str, command):
        self.updated.append((model_id, command))
        return _model_payload(model_id=model_id, enabled=command.enabled if command.enabled is not None else True)

    async def set_model_catalog_default(self, model_id: str, *, admin_id: str | None = None):
        self.defaults.append((model_id, admin_id))
        return _model_payload(model_id=model_id, is_default=True)

    async def update_model_catalog_health(self, model_id: str, command):
        self.health_updates.append((model_id, command))
        return _model_payload(model_id=model_id, health_status=command.status)

    async def update_model_capability_assessment(self, model_id: str, command):
        self.capability_updates.append((model_id, command))
        return _model_payload(model_id=model_id, health_status="healthy")


@pytest.mark.asyncio
async def test_create_model_passes_admin_id_to_dataservice() -> None:
    dataservice = _FakeDataService()
    service = ModelCatalogService(dataservice=dataservice)  # type: ignore[arg-type]

    record = await service.create_model(
        {
            "model_id": "deepseek-v3",
            "display_name": "DeepSeek V3",
            "model_name": "deepseek/deepseek-v3",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-live-1234abcd",
            "generation_api": "chat_completions",
        },
        admin_id="admin-1",
    )

    assert record.model_id == "deepseek-v3"
    assert dataservice.created.admin_id == "admin-1"
    assert dataservice.created.api_key == "sk-live-1234abcd"


@pytest.mark.asyncio
async def test_update_model_drops_blank_api_key_to_preserve_secret() -> None:
    dataservice = _FakeDataService()
    service = ModelCatalogService(dataservice=dataservice)  # type: ignore[arg-type]

    await service.update_model("deepseek-v3", {"display_name": "DeepSeek V3.1", "api_key": ""}, admin_id="admin-1")

    _model_id, command = dataservice.updated[0]
    assert command.display_name == "DeepSeek V3.1"
    assert command.api_key is None
    assert "api_key" not in command.model_fields_set
    assert command.admin_id == "admin-1"


@pytest.mark.asyncio
async def test_update_model_preserves_clearable_null_fields() -> None:
    dataservice = _FakeDataService()
    service = ModelCatalogService(dataservice=dataservice)  # type: ignore[arg-type]

    await service.update_model(
        "deepseek-v3",
        {
            "pricing_policy_id": None,
            "timeout_seconds": None,
            "default_headers": None,
            "api_key": "",
        },
        admin_id="admin-1",
    )

    _model_id, command = dataservice.updated[0]
    assert command.pricing_policy_id is None
    assert command.timeout_seconds is None
    assert command.default_headers is None
    assert "pricing_policy_id" in command.model_fields_set
    assert "timeout_seconds" in command.model_fields_set
    assert "default_headers" in command.model_fields_set
    assert "api_key" not in command.model_fields_set


@pytest.mark.asyncio
async def test_disable_model_uses_dataservice_update_invariant() -> None:
    dataservice = _FakeDataService()
    service = ModelCatalogService(dataservice=dataservice)  # type: ignore[arg-type]

    await service.disable_model("deepseek-v3", admin_id="admin-1")

    model_id, command = dataservice.updated[0]
    assert model_id == "deepseek-v3"
    assert command.enabled is False
    assert command.admin_id == "admin-1"


@pytest.mark.asyncio
async def test_test_model_records_probe_backed_assessment(monkeypatch) -> None:
    dataservice = _FakeDataService()
    dataservice.runtime_items = [
        _runtime_payload(
            model_id="gpt-5.6-sol",
            display_name="GPT-5.6 Sol",
            provider_name="OpenAI",
            model_name="gpt-5.6-sol",
            base_url="https://api.nainai.love/v1",
        )
    ]
    service = ModelCatalogService(dataservice=dataservice)  # type: ignore[arg-type]
    assessment = verified_capability_assessment("gpt-5.6-sol")

    async def _probe(_target):
        return assessment

    monkeypatch.setattr(
        "src.services.model_catalog_service.probe_model_capabilities",
        _probe,
    )

    record = await service.test_model("gpt-5.6-sol")

    assert record is not None
    assert record.health_status == "healthy"
    _model_id, command = dataservice.capability_updates[0]
    assert command.profile == assessment.profile
    assert command.evidence == assessment.evidence


@pytest.mark.asyncio
async def test_test_model_can_probe_a_disabled_catalog_entry(monkeypatch) -> None:
    dataservice = _FakeDataService()
    dataservice.runtime_items = [
        _runtime_payload(
            model_id="disabled-model",
            display_name="GPT-5.6 Sol",
            provider_name="OpenAI",
            model_name="gpt-5.6-sol",
            base_url="https://api.nainai.love/v1",
        )
    ]
    service = ModelCatalogService(dataservice=dataservice)  # type: ignore[arg-type]
    assessment = verified_capability_assessment("gpt-5.6-sol")

    async def _probe(_target):
        return assessment

    monkeypatch.setattr(
        "src.services.model_catalog_service.probe_model_capabilities",
        _probe,
    )

    record = await service.test_model("disabled-model")

    assert record is not None
    assert record.health_status == "healthy"
    assert dataservice.capability_updates[0][0] == "disabled-model"
    assert dataservice.health_updates == []


@pytest.mark.asyncio
async def test_test_model_marks_missing_catalog_entry_failed() -> None:
    dataservice = _FakeDataService()
    dataservice.runtime_items = []
    service = ModelCatalogService(dataservice=dataservice)  # type: ignore[arg-type]

    record = await service.test_model("missing-model")

    assert record is not None
    assert record.health_status == "failed"
    _model_id, command = dataservice.health_updates[0]
    assert command.status == "failed"
    assert "not found" in str(command.error_message)


@pytest.mark.asyncio
async def test_public_models_request_enabled_models_only() -> None:
    dataservice = _FakeDataService()
    service = ModelCatalogService(dataservice=dataservice)  # type: ignore[arg-type]

    models = await service.list_public_models(purpose="chat")

    assert [model.model_id for model in models] == ["enabled-model"]
