"""Tests for profile-backed model routing."""

from __future__ import annotations

import pytest

from src.models.capability_profile import (
    GenerationAPI,
    gpt55_release_assessment,
    unverified_capability_assessment,
)
from src.models.router import (
    InvalidRequestedModelError,
    list_user_selectable_models,
    model_supports_reasoning_effort,
    model_supports_thinking,
    model_supports_vision,
    route_chat_model,
    route_image_model,
    route_model,
    validate_requested_model,
)
from src.services.model_catalog_cache import (
    RuntimeModelConfig,
    install_model_catalog_snapshot,
    reset_model_catalog_cache,
)


def _runtime_model(
    *,
    model_id: str = "gpt-5.5",
    category: str = "llm",
    is_default: bool = True,
    base_url: str = "https://api.nainai.love/v1",
    verified: bool = True,
) -> RuntimeModelConfig:
    if verified:
        assessment = gpt55_release_assessment()
        model_name = "gpt-5.5"
        generation_api = GenerationAPI.CHAT_COMPLETIONS
    else:
        model_name = model_id
        generation_api = (
            GenerationAPI.CHAT_COMPLETIONS if category == "llm" else None
        )
        assessment = unverified_capability_assessment(
            model_id=model_id,
            model_name=model_name,
            base_url=base_url,
            generation_api=generation_api,
        )
    return RuntimeModelConfig(
        id=model_id,
        name=model_id,
        category=category,
        provider="OpenAI" if category == "llm" else "Image Provider",
        model=model_name,
        api_key="sk-test",
        base_url=base_url,
        generation_api=generation_api,
        max_tokens=128000,
        temperature=0.3,
        timeout_seconds=30,
        max_retries=0,
        capability_profile=assessment.profile,
        capability_probe=assessment.evidence,
        capability_probe_hash=assessment.profile.probe_hash,
        capability_observed_at=assessment.profile.observed_at,
        default_headers={},
        pricing_policy_id="model-standard",
        is_default=is_default,
        config_version=1,
    )


@pytest.fixture(autouse=True)
def _catalog():
    reset_model_catalog_cache()
    install_model_catalog_snapshot(
        [
            _runtime_model(),
            _runtime_model(
                model_id="image-gen",
                category="image",
                is_default=False,
                base_url="https://images.example/v1",
                verified=False,
            ),
        ]
    )
    yield
    reset_model_catalog_cache()


def test_explicit_verified_chat_model_is_honored() -> None:
    assert route_chat_model(requested_model="gpt-5.5") == "gpt-5.5"
    assert validate_requested_model("gpt-5.5", require_tools=True) == "gpt-5.5"
    assert validate_requested_model("default", require_tools=True) == "default"


def test_unknown_explicit_model_is_never_silently_rerouted() -> None:
    with pytest.raises(InvalidRequestedModelError, match="Unknown model id"):
        validate_requested_model("missing-model")
    with pytest.raises(InvalidRequestedModelError, match="Requested model"):
        route_chat_model(requested_model="missing-model")


def test_unverified_tool_model_is_rejected_instead_of_using_default() -> None:
    install_model_catalog_snapshot(
        [
            _runtime_model(
                model_id="unverified",
                category="llm",
                verified=False,
            )
        ]
    )

    with pytest.raises(ValueError, match="No models configured for required routing"):
        route_chat_model(require_tools=True)
    with pytest.raises(InvalidRequestedModelError, match="strict-tool capability probe"):
        validate_requested_model("unverified", require_tools=True)


def test_capabilities_are_not_inferred_from_unknown_model_names() -> None:
    assert model_supports_vision("qwen-vl-plus") is False
    assert model_supports_thinking("gpt-5.5-name-only") is False
    assert model_supports_reasoning_effort("gpt-5.5-name-only") is False


def test_reasoning_support_comes_from_current_profile() -> None:
    assert model_supports_thinking("gpt-5.5") is True
    assert model_supports_reasoning_effort("gpt-5.5") is True
    assert model_supports_vision("gpt-5.5") is False


def test_image_routing_remains_category_based() -> None:
    assert route_image_model(requested_model="image-gen") == "image-gen"
    assert validate_requested_model(
        "image-gen",
        allowed_categories=("image",),
    ) == "image-gen"
    assert [item.id for item in list_user_selectable_models(purpose="image")] == [
        "image-gen"
    ]
    assert validate_requested_model(
        "image-gen",
        allowed_categories=("llm", "image"),
    ) == "image-gen"


def test_multi_category_routing_honors_preference_order_deterministically() -> None:
    assert (
        route_model(
            preferred_categories=("image", "llm"),
            allowed_categories=("llm", "image"),
        )
        == "image-gen"
    )


def test_stale_profile_rejects_selected_model() -> None:
    stale = _runtime_model(base_url="https://changed.example/v1")
    install_model_catalog_snapshot([stale])

    with pytest.raises(InvalidRequestedModelError, match="strict-tool capability probe"):
        route_chat_model(requested_model="gpt-5.5")

    with pytest.raises(InvalidRequestedModelError, match="strict-tool capability probe"):
        validate_requested_model("default", require_tools=True)
