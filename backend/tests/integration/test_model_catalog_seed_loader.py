"""Model catalog seed import tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.dataservice.domains.model_catalog.seed_loader import DataServiceModelCatalogSeedLoader


class _FakeModelCatalogService:
    def __init__(self, existing: list[Any] | None = None) -> None:
        self.existing = list(existing or [])
        self.created: list[tuple[dict[str, Any], str | None]] = []

    async def list_models(self):
        return [*self.existing, *[SimpleNamespace(**data) for data, _admin_id in self.created]]

    async def create_model(self, data: dict[str, Any], *, admin_id: str | None = None):
        self.created.append((dict(data), admin_id))
        return SimpleNamespace(**data)

    async def update_capability_assessment(self, model_id: str, *, profile, evidence):
        return SimpleNamespace(model_id=model_id, profile=profile, evidence=evidence)


@pytest.mark.asyncio
async def test_model_catalog_seed_loader_imports_env_models_when_empty() -> None:
    service = _FakeModelCatalogService()
    source = {
        "PROVIDER_API_KEY": "sk-shared-123456",
        "LLM_DEFAULT_MODEL": "deepseek-chat",
        "LLM_MODELS": json.dumps(
            [
                {
                    "id": "deepseek-chat",
                    "name": "DeepSeek Chat",
                    "model": "deepseek-chat",
                    "api_key_env": "PROVIDER_API_KEY",
                    "base_url": "https://api.example.com/v1",
                    "generation_api": "chat_completions",
                    "provider_name": "OpenAI",
                    "trust_level": "custom",
                    "pricing_policy_id": "deepseek-chat-policy",
                }
            ]
        ),
        "LLM_IMAGE_MODELS": json.dumps(
            [
                {
                    "id": "image-gen",
                    "model": "image-gen-v1",
                    "api_key_env": "PROVIDER_API_KEY",
                    "base_url": "https://images.example.com/v1",
                }
            ]
        ),
    }

    loaded = await DataServiceModelCatalogSeedLoader(
        service,  # type: ignore[arg-type]
        source=source,
        admin_id="admin@example.com",
    ).load_seeds_if_empty()

    assert loaded == 2
    llm_seed, admin_id = service.created[0]
    assert admin_id == "admin@example.com"
    assert llm_seed["model_id"] == "deepseek-chat"
    assert llm_seed["display_name"] == "DeepSeek Chat"
    assert llm_seed["category"] == "llm"
    assert llm_seed["is_default"] is True
    assert llm_seed["generation_api"] == "chat_completions"
    assert llm_seed["provider_name"] == "OpenAI"
    assert llm_seed["api_key"] == "sk-shared-123456"
    assert "supports_tools" not in llm_seed
    assert llm_seed["pricing_policy_id"] == "deepseek-chat-policy"
    image_seed, _admin_id = service.created[1]
    assert image_seed["category"] == "image"
    assert image_seed["is_default"] is False
    assert image_seed["api_key"] == "sk-shared-123456"


@pytest.mark.asyncio
async def test_model_catalog_seed_loader_binds_enabled_env_models_to_default_pricing_policy() -> None:
    service = _FakeModelCatalogService()
    source = {
        "PROVIDER_API_KEY": "sk-shared-123456",
        "LLM_MODELS": json.dumps(
            [
                {
                    "id": "mimo-v2",
                    "name": "MiMo V2",
                    "model": "mimo-v2",
                    "api_key_env": "PROVIDER_API_KEY",
                    "base_url": "https://api.example.com/v1",
                    "generation_api": "chat_completions",
                }
            ]
        ),
        "LLM_IMAGE_MODELS": json.dumps(
            [
                {
                    "id": "image-gen",
                    "model": "image-gen-v1",
                    "api_key_env": "PROVIDER_API_KEY",
                    "base_url": "https://images.example.com/v1",
                }
            ]
        ),
    }

    loaded = await DataServiceModelCatalogSeedLoader(
        service,  # type: ignore[arg-type]
        source=source,
        default_pricing_policy_id="default-model-usage",
    ).load_seeds_if_empty()

    assert loaded == 2
    assert [seed["pricing_policy_id"] for seed, _admin_id in service.created] == [
        "default-model-usage",
        "default-model-usage",
    ]


@pytest.mark.asyncio
async def test_model_catalog_seed_loader_does_not_overwrite_existing_catalog() -> None:
    service = _FakeModelCatalogService(existing=[SimpleNamespace(model_id="existing")])
    source = {
        "PROVIDER_API_KEY": "sk-shared-123456",
        "LLM_MODELS": json.dumps(
            [
                {
                    "id": "new-model",
                    "model": "new-model",
                    "api_key_env": "PROVIDER_API_KEY",
                    "base_url": "https://api.example.com/v1",
                    "generation_api": "chat_completions",
                }
            ]
        )
    }

    loaded = await DataServiceModelCatalogSeedLoader(
        service,  # type: ignore[arg-type]
        source=source,
    ).load_seeds_if_empty()

    assert loaded == 0
    assert service.created == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source, message",
    [
        ({"LLM_MODELS": "{"}, "LLM_MODELS must contain valid JSON"),
        ({"LLM_MODELS": json.dumps({"id": "not-a-list"})}, "LLM_MODELS must be a JSON list"),
        ({"LLM_MODELS": json.dumps(["not-an-object"])}, "LLM_MODELS entries must be objects"),
        (
            {
                "LLM_MODELS": json.dumps(
                    [
                        {
                            "id": "broken",
                            "model": "broken",
                            "base_url": "https://api.example.com/v1",
                        }
                    ]
                )
            },
            "invalid llm model catalog seed 'broken'",
        ),
    ],
)
async def test_model_catalog_seed_loader_rejects_invalid_seed_config(
    source: dict[str, str],
    message: str,
) -> None:
    service = _FakeModelCatalogService()

    with pytest.raises(ValueError, match=message):
        await DataServiceModelCatalogSeedLoader(
            service,  # type: ignore[arg-type]
            source=source,
        ).load_seeds_if_empty()

    assert service.created == []
