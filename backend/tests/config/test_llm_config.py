"""Tests for env bootstrap into the DataService-shaped model cache."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from src.config.llm_config import (
    get_image_models,
    get_llm_models,
    get_model_full_config,
    reload_models,
)
from src.models.capability_profile import GenerationAPI


@pytest.fixture(autouse=True)
def _reset_models():
    with patch.dict(
        os.environ,
        {"LLM_MODELS": "", "LLM_IMAGE_MODELS": "", "LLM_DEFAULT_MODEL": ""},
        clear=False,
    ):
        reload_models()
        yield
        reload_models()


def _gpt_seed() -> str:
    return json.dumps(
        [
            {
                "id": "gpt-5.6-sol",
                "name": "GPT-5.6 Sol",
                "model": "gpt-5.6-sol",
                "api_key": "sk-test",
                "base_url": "https://api.nainai.love/v1",
                "generation_api": "chat_completions",
                "max_tokens": 128000,
            }
        ]
    )


def test_env_seed_parses_generation_api_without_capability_flags() -> None:
    with patch.dict(
        os.environ,
        {"LLM_MODELS": _gpt_seed(), "LLM_DEFAULT_MODEL": "gpt-5.6-sol"},
        clear=False,
    ):
        reload_models()
        models = get_llm_models()

    assert [model.id for model in models] == ["gpt-5.6-sol"]
    assert models[0].generation_api is GenerationAPI.CHAT_COMPLETIONS
    assert models[0].capability_profile is not None
    assert models[0].capability_profile.protocol_conformance is False


def test_removed_capability_switches_are_rejected_not_hydrated() -> None:
    stale = json.loads(_gpt_seed())
    stale[0]["supports_tools"] = True

    with patch.dict(
        os.environ,
        {"LLM_MODELS": json.dumps(stale), "LLM_DEFAULT_MODEL": ""},
        clear=False,
    ):
        reload_models()
        assert get_llm_models() == []


def test_image_seed_remains_available_without_language_generation_api() -> None:
    image_seed = json.dumps(
        [
            {
                "id": "image-gen",
                "model": "image-gen-v1",
                "api_key": "sk-image",
                "base_url": "https://images.example/v1",
            }
        ]
    )
    with patch.dict(
        os.environ,
        {"LLM_MODELS": "", "LLM_IMAGE_MODELS": image_seed},
        clear=False,
    ):
        reload_models()
        models = get_image_models()

    assert [model.id for model in models] == ["image-gen"]
    assert models[0].generation_api is None
    assert models[0].capability_profile is not None


def test_full_config_exposes_typed_assessment_not_mirrored_booleans() -> None:
    with patch.dict(
        os.environ,
        {"LLM_MODELS": _gpt_seed(), "LLM_DEFAULT_MODEL": "gpt-5.6-sol"},
        clear=False,
    ):
        reload_models()
        config = get_model_full_config("gpt-5.6-sol")

    assert config["generation_api"] is GenerationAPI.CHAT_COMPLETIONS
    assert config["capability_profile"].model_id == "gpt-5.6-sol"
    assert config["capability_probe"].model_id == "gpt-5.6-sol"
    assert not any(key.startswith("supports_") for key in config)


def test_unknown_model_is_not_rerouted() -> None:
    with patch.dict(
        os.environ,
        {"LLM_MODELS": _gpt_seed(), "LLM_DEFAULT_MODEL": "gpt-5.6-sol"},
        clear=False,
    ):
        reload_models()
        with pytest.raises(ValueError, match="Model not found"):
            get_model_full_config("missing-model")


def test_invalid_explicit_default_fails_closed() -> None:
    with patch.dict(
        os.environ,
        {"LLM_MODELS": _gpt_seed(), "LLM_DEFAULT_MODEL": "missing-model"},
        clear=False,
    ):
        llms, images = reload_models()

    assert llms == {}
    assert images == {}
