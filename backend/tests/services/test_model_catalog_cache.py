"""Tests for runtime model catalog cache."""

from __future__ import annotations

import pytest

from src.dataservice_client.contracts.model_catalog import ModelRuntimeConfigPayload
from src.services.model_catalog_cache import (
    get_default_runtime_model_id,
    get_model_catalog_snapshot,
    get_runtime_model_config,
    install_model_catalog_snapshot,
    refresh_model_catalog_cache,
    reset_model_catalog_cache,
    resolve_runtime_model_id,
)


def _runtime_model(**overrides) -> ModelRuntimeConfigPayload:
    data = {
        "model_id": "deepseek-v3",
        "display_name": "DeepSeek V3",
        "provider_protocol": "openai_compatible",
        "provider_name": "QnAIGC",
        "category": "llm",
        "model_name": "deepseek/deepseek-v3",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-live-1234abcd",
        "is_default": True,
        "supports_tools": True,
        "supports_reasoning_effort": True,
        "max_tokens": 8192,
        "temperature": 0.3,
        "config_version": 1,
        "default_headers": {"X-Provider": "qnaigc"},
    }
    data.update(overrides)
    return ModelRuntimeConfigPayload.model_validate(data)


class _FakeDataService:
    def __init__(self) -> None:
        self.items = [_runtime_model()]

    async def list_model_catalog_runtime_models(self, *, category: str | None = None):
        return [item for item in self.items if category is None or item.category == category]


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_model_catalog_cache()
    yield
    reset_model_catalog_cache()


@pytest.mark.asyncio
async def test_cache_loads_runtime_config_from_dataservice() -> None:
    await refresh_model_catalog_cache(_FakeDataService())  # type: ignore[arg-type]

    config = get_runtime_model_config("deepseek-v3")

    assert config is not None
    assert config.api_key == "sk-live-1234abcd"
    assert config.model == "deepseek/deepseek-v3"
    assert config.default_headers == {"X-Provider": "qnaigc"}


@pytest.mark.asyncio
async def test_version_change_refreshes_snapshot() -> None:
    dataservice = _FakeDataService()
    await refresh_model_catalog_cache(dataservice)  # type: ignore[arg-type]
    assert get_model_catalog_snapshot().version == 1

    dataservice.items = [_runtime_model(display_name="DeepSeek V3.1", config_version=2)]
    await refresh_model_catalog_cache(dataservice)  # type: ignore[arg-type]

    snapshot = get_model_catalog_snapshot()
    assert snapshot.version == 2
    assert snapshot.by_id["deepseek-v3"].name == "DeepSeek V3.1"


def test_resolve_default_returns_catalog_default() -> None:
    install_model_catalog_snapshot(
        [
            _runtime_model(model_id="first", is_default=False),
            _runtime_model(model_id="default-model", is_default=True),
        ]
    )

    assert get_default_runtime_model_id() == "default-model"
    assert resolve_runtime_model_id("default") == "default-model"


def test_execution_safe_snapshot_excludes_api_key() -> None:
    install_model_catalog_snapshot([_runtime_model()])

    safe_model = get_model_catalog_snapshot().safe_models()[0]

    assert safe_model["model_id"] == "deepseek-v3"
    assert "api_key" not in safe_model
