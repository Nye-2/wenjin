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


@pytest.mark.asyncio
async def test_model_catalog_seed_loader_imports_env_models_when_empty() -> None:
    service = _FakeModelCatalogService()
    source = {
        "LLM_DEFAULT_MODEL": "deepseek-chat",
        "LLM_MODELS": json.dumps(
            [
                {
                    "id": "deepseek-chat",
                    "name": "DeepSeek Chat",
                    "model": "deepseek-chat",
                    "api_key": "sk-test-123456",
                    "base_url": "https://api.example.com/v1",
                    "supports_tools": True,
                    "supports_thinking": True,
                    "pricing_policy_id": "deepseek-chat-policy",
                }
            ]
        ),
        "LLM_IMAGE_MODELS": json.dumps(
            [
                {
                    "id": "image-gen",
                    "model": "image-gen-v1",
                    "api_key": "sk-image-123456",
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
    assert llm_seed["supports_tools"] is True
    assert llm_seed["supports_reasoning_effort"] is True
    assert llm_seed["pricing_policy_id"] == "deepseek-chat-policy"
    image_seed, _admin_id = service.created[1]
    assert image_seed["category"] == "image"
    assert image_seed["is_default"] is False


@pytest.mark.asyncio
async def test_model_catalog_seed_loader_does_not_overwrite_existing_catalog() -> None:
    service = _FakeModelCatalogService(existing=[SimpleNamespace(model_id="existing")])
    source = {
        "LLM_MODELS": json.dumps(
            [
                {
                    "id": "new-model",
                    "model": "new-model",
                    "api_key": "sk-test-123456",
                    "base_url": "https://api.example.com/v1",
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
