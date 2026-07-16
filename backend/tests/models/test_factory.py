"""Tests for the probe-backed Chat Completions model factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.models.capability_profile import gpt56_release_assessment
from src.models.factory import create_chat_model
from src.services.model_catalog_cache import (
    RuntimeModelConfig,
    install_model_catalog_snapshot,
    reset_model_catalog_cache,
)


def _runtime_model(*, base_url: str = "https://api.nainai.love/v1") -> RuntimeModelConfig:
    assessment = gpt56_release_assessment("gpt-5.6-sol")
    return RuntimeModelConfig(
        id="gpt-5.6-sol",
        name="GPT-5.6 Sol",
        category="llm",
        provider="OpenAI",
        model="gpt-5.6-sol",
        api_key="sk-test",
        base_url=base_url,
        generation_api=assessment.profile.generation_api,
        max_tokens=128000,
        temperature=0.3,
        timeout_seconds=45,
        max_retries=1,
        capability_profile=assessment.profile,
        capability_probe=assessment.evidence,
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
        default_headers={"X-Test": "1"},
        pricing_policy_id="model-standard",
        is_default=True,
        config_version=1,
    )


@pytest.fixture(autouse=True)
def _catalog():
    reset_model_catalog_cache()
    install_model_catalog_snapshot([_runtime_model()])
    yield
    reset_model_catalog_cache()


def test_factory_uses_only_chat_completions_xhigh_and_store_false() -> None:
    sentinel = object()
    with patch("src.models.factory.ReasoningChatOpenAI", return_value=sentinel) as model_cls:
        result = create_chat_model("gpt-5.6-sol")

    assert result is sentinel
    kwargs = model_cls.call_args.kwargs
    assert kwargs["model"] == "gpt-5.6-sol"
    assert kwargs["base_url"] == "https://api.nainai.love/v1"
    assert kwargs["reasoning_effort"] == "xhigh"
    assert kwargs["store"] is False
    assert kwargs["timeout"] == 45
    assert kwargs["max_retries"] == 1
    assert kwargs["http_client"]._trust_env is False
    assert kwargs["http_async_client"]._trust_env is False
    assert "use_responses_api" not in kwargs


def test_factory_honors_explicit_transport_limits() -> None:
    with patch("src.models.factory.ReasoningChatOpenAI") as model_cls:
        create_chat_model(
            "gpt-5.6-sol",
            request_timeout=12,
            max_retries=0,
            max_output_tokens=32000,
        )

    kwargs = model_cls.call_args.kwargs
    assert kwargs["timeout"] == 12
    assert kwargs["max_retries"] == 0
    assert kwargs["max_tokens"] == 32000


def test_factory_bounds_call_output_budget_by_catalog_limit() -> None:
    with patch("src.models.factory.ReasoningChatOpenAI") as model_cls:
        create_chat_model("gpt-5.6-sol", max_output_tokens=256000)

    assert model_cls.call_args.kwargs["max_tokens"] == 128000


@pytest.mark.parametrize("value", [0, -1])
def test_factory_rejects_non_positive_call_output_budget(value: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        create_chat_model("gpt-5.6-sol", max_output_tokens=value)


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh"])
def test_factory_accepts_every_probed_reasoning_effort(effort: str) -> None:
    with patch("src.models.factory.ReasoningChatOpenAI") as model_cls:
        create_chat_model("gpt-5.6-sol", reasoning_effort=effort)

    assert model_cls.call_args.kwargs["reasoning_effort"] == effort


def test_factory_rejects_unknown_reasoning_effort() -> None:
    with pytest.raises(ValueError, match="Unsupported reasoning_effort"):
        create_chat_model("gpt-5.6-sol", reasoning_effort="extreme")


def test_factory_rejects_stale_endpoint_profile() -> None:
    install_model_catalog_snapshot(
        [_runtime_model(base_url="https://changed.example/v1")]
    )

    with pytest.raises(ValueError, match="endpoint_changed"):
        create_chat_model("gpt-5.6-sol")


def test_factory_rejects_unknown_model_without_rerouting() -> None:
    with pytest.raises(ValueError, match="Unknown model id"):
        create_chat_model("missing-model")
