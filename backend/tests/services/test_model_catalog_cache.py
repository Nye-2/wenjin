"""Tests for runtime model catalog cache."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.dataservice_client.contracts.model_catalog import ModelRuntimeConfigPayload
from src.models.capability_profile import (
    GenerationAPI,
    unverified_capability_assessment,
)
from src.services.model_catalog_cache import (
    MODEL_CAPABILITY_MAX_AGE,
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
        "generation_api": "chat_completions",
        "provider_name": "QnAIGC",
        "category": "llm",
        "model_name": "deepseek/deepseek-v3",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-live-1234abcd",
        "is_default": True,
        "max_tokens": 8192,
        "temperature": 0.3,
        "timeout_seconds": 30,
        "max_retries": 1,
        "pricing_policy_id": "deepseek-chat-policy",
        "config_version": 1,
        "default_headers": {"X-Provider": "qnaigc"},
    }
    data.update(overrides)
    assessment = unverified_capability_assessment(
        model_id=data["model_id"],
        model_name=data["model_name"],
        base_url=data["base_url"],
        generation_api=GenerationAPI(data["generation_api"]),
    )
    data.update(
        {
            "capability_profile": assessment.profile,
            "capability_probe": assessment.evidence,
            "capability_probe_hash": assessment.profile.probe_hash,
            "capability_observed_at": assessment.profile.observed_at,
        }
    )
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
    assert config.pricing_policy_id == "deepseek-chat-policy"
    assert config.default_headers == {"X-Provider": "qnaigc"}
    assert config.capability_freshness().current is True


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
    assert safe_model["pricing_policy_id"] == "deepseek-chat-policy"
    assert safe_model["capability_profile"]["protocol_conformance"] is False
    assert "api_key" not in safe_model


def test_execution_safe_snapshot_redacts_secret_default_headers() -> None:
    install_model_catalog_snapshot(
        [
            _runtime_model(
                default_headers={
                    "api-key": "tp-cvt-secret-token",
                    "X-Provider": "qnaigc",
                }
            )
        ]
    )

    safe_model = get_model_catalog_snapshot().safe_models()[0]

    assert safe_model["default_headers"] == {"api-key": "[redacted]", "X-Provider": "qnaigc"}


def test_cache_rejects_probe_hash_mismatch() -> None:
    payload = _runtime_model()
    tampered = payload.model_copy(update={"capability_probe_hash": "0" * 64})

    with pytest.raises(ValueError, match="probe hash is inconsistent"):
        install_model_catalog_snapshot([tampered])


def test_cache_rejects_profile_and_evidence_from_different_probes() -> None:
    payload = _runtime_model()
    other = unverified_capability_assessment(
        model_id=payload.model_id,
        model_name=payload.model_name,
        base_url="https://other.example/v1",
        generation_api=GenerationAPI.CHAT_COMPLETIONS,
    )
    tampered = payload.model_copy(update={"capability_probe": other.evidence})

    with pytest.raises(ValueError, match="not derived from the supplied probe"):
        install_model_catalog_snapshot([tampered])


def test_capability_freshness_uses_runtime_max_age_policy() -> None:
    install_model_catalog_snapshot([_runtime_model()])
    config = get_runtime_model_config("deepseek-v3")

    assert config is not None
    observed_at = config.capability_observed_at
    assert config.capability_freshness(
        now=observed_at + MODEL_CAPABILITY_MAX_AGE,
    ).current is True

    stale = config.capability_freshness(
        now=observed_at + MODEL_CAPABILITY_MAX_AGE + timedelta(microseconds=1),
    )
    assert stale.current is False
    assert stale.reasons == ("probe_stale",)
