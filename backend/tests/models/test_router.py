"""Tests for runtime model routing."""

import json
import os
from collections.abc import Generator
from unittest.mock import patch

import pytest

from src.config.llm_config import reload_models
from src.models.router import (
    InvalidRequestedModelError,
    list_user_selectable_models,
    model_supports_reasoning_effort,
    model_supports_thinking,
    model_supports_vision,
    route_chat_model,
    route_image_model,
    route_writing_model,
    validate_requested_model,
)


@pytest.fixture(autouse=True)
def _reset_model_cache() -> Generator[None, None, None]:
    reload_models()
    yield
    reload_models()


def test_route_prefers_explicit_user_model() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-primary",
            "model": "provider/llm-primary",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_MODELS": llm_models, "LLM_DEFAULT_MODEL": "llm-primary"},
        clear=False,
    ):
        reload_models()
        model_id = route_chat_model(
            requested_model="llm-primary",
            thread_model="some-thread-model",
        )
        assert model_id == "llm-primary"


def test_route_uses_thread_model_when_request_not_specified() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-primary",
            "model": "provider/llm-primary",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_MODELS": llm_models, "LLM_DEFAULT_MODEL": "llm-primary"},
        clear=False,
    ):
        reload_models()
        model_id = route_chat_model(
            requested_model=None,
            thread_model="llm-primary",
        )
        assert model_id == "llm-primary"


def test_validate_requested_model_rejects_unknown_model() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-primary",
            "model": "provider/llm-primary",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_MODELS": llm_models, "LLM_DEFAULT_MODEL": "llm-primary"},
        clear=False,
    ):
        reload_models()
        with pytest.raises(InvalidRequestedModelError, match="Unknown model id"):
            validate_requested_model("missing-model", allowed_categories=("llm",))


def test_validate_requested_model_rejects_image_for_non_image_task() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-primary",
            "model": "provider/llm-primary",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
        }
    ])
    image_models = json.dumps([
        {
            "id": "img-primary",
            "model": "provider/img-primary",
            "api_key": "sk-img",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {
            "LLM_MODELS": llm_models,
            "LLM_IMAGE_MODELS": image_models,
            "LLM_DEFAULT_MODEL": "llm-primary",
        },
        clear=False,
    ):
        reload_models()
        with pytest.raises(InvalidRequestedModelError, match="image model"):
            validate_requested_model("img-primary", allowed_categories=("llm",))


def test_validate_requested_model_accepts_image_for_image_task() -> None:
    image_models = json.dumps([
        {
            "id": "img-primary",
            "model": "provider/img-primary",
            "api_key": "sk-img",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_IMAGE_MODELS": image_models, "LLM_DEFAULT_MODEL": "img-primary"},
        clear=False,
    ):
        reload_models()
        assert validate_requested_model("img-primary", allowed_categories=("image",)) == "img-primary"


def test_route_picks_first_tool_capable_candidate_when_no_selection() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-tool",
            "model": "provider/llm-tool",
            "api_key": "sk-tool",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        },
        {
            "id": "llm-plain",
            "model": "provider/llm-plain",
            "api_key": "sk-plain",
            "base_url": "https://example.com/v1",
        },
    ])
    with patch.dict(
        os.environ,
        {
            "LLM_MODELS": llm_models,
            "LLM_DEFAULT_MODEL": "llm-plain",
        },
        clear=False,
    ):
        reload_models()
        model_id = route_chat_model(requested_model=None, thread_model=None, require_tools=True)
        assert model_id == "llm-tool"


def test_route_falls_back_to_default_when_no_tool_capable_models() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-plain",
            "model": "provider/llm-plain",
            "api_key": "sk-plain",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_MODELS": llm_models, "LLM_DEFAULT_MODEL": "llm-plain"},
        clear=False,
    ):
        reload_models()
        model_id = route_chat_model(requested_model=None, thread_model=None, require_tools=True)
        assert model_id == "llm-plain"


def test_route_writing_selects_from_llm_models() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-primary",
            "model": "provider/llm-primary",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
        },
        {
            "id": "llm-secondary",
            "model": "provider/llm-secondary",
            "api_key": "sk-llm2",
            "base_url": "https://example.com/v1",
        },
    ])
    with patch.dict(
        os.environ,
        {
            "LLM_MODELS": llm_models,
            "LLM_DEFAULT_MODEL": "llm-primary",
        },
        clear=False,
    ):
        reload_models()
        model_id = route_writing_model()
        assert model_id == "llm-primary"


def test_list_user_selectable_models_returns_all_llm_for_chat() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-primary",
            "model": "provider/llm-primary",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
        },
        {
            "id": "llm-secondary",
            "model": "provider/llm-secondary",
            "api_key": "sk-llm2",
            "base_url": "https://example.com/v1",
        },
    ])
    with patch.dict(
        os.environ,
        {"LLM_MODELS": llm_models},
        clear=False,
    ):
        reload_models()
        selectable = list_user_selectable_models(purpose="chat")
        selectable_ids = [model.id for model in selectable]
        assert "llm-primary" in selectable_ids
        assert "llm-secondary" in selectable_ids


def test_list_user_selectable_models_returns_image_models_for_image() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-primary",
            "model": "provider/llm-primary",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
        }
    ])
    image_models = json.dumps([
        {
            "id": "img-primary",
            "model": "provider/img-primary",
            "api_key": "sk-img",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_MODELS": llm_models, "LLM_IMAGE_MODELS": image_models},
        clear=False,
    ):
        reload_models()
        selectable = list_user_selectable_models(purpose="image")
        selectable_ids = [model.id for model in selectable]
        assert "img-primary" in selectable_ids
        assert "llm-primary" not in selectable_ids


def test_route_image_model_selects_from_image_models() -> None:
    image_models = json.dumps([
        {
            "id": "img-primary",
            "model": "provider/img-primary",
            "api_key": "sk-img",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_IMAGE_MODELS": image_models, "LLM_DEFAULT_MODEL": "img-primary"},
        clear=False,
    ):
        reload_models()
        model_id = route_image_model()
        assert model_id == "img-primary"


def test_model_supports_vision_honors_explicit_flag() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-vision",
            "model": "provider/llm-vision",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
            "supports_vision": True,
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_MODELS": llm_models},
        clear=False,
    ):
        reload_models()
        assert model_supports_vision("llm-vision") is True


def test_model_supports_vision_uses_name_hints_for_unknown_model() -> None:
    assert model_supports_vision("qwen-vl-plus") is True
    assert model_supports_vision("plain-text-model") is False


def test_model_supports_thinking_honors_explicit_flag() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-think",
            "model": "provider/llm-think",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
            "supports_thinking": True,
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_MODELS": llm_models},
        clear=False,
    ):
        reload_models()
        assert model_supports_thinking("llm-think") is True
        assert model_supports_thinking("llm-plain") is False


def test_model_supports_reasoning_effort_honors_explicit_flag() -> None:
    llm_models = json.dumps([
        {
            "id": "llm-reasoning",
            "model": "provider/llm-reasoning",
            "api_key": "sk-llm",
            "base_url": "https://example.com/v1",
            "supports_reasoning_effort": True,
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_MODELS": llm_models},
        clear=False,
    ):
        reload_models()
        assert model_supports_reasoning_effort("llm-reasoning") is True
        assert model_supports_reasoning_effort("llm-plain") is False
