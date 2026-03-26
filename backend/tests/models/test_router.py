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
    route_chat_model,
    route_writing_model,
    validate_requested_model,
)


@pytest.fixture(autouse=True)
def _reset_model_cache() -> Generator[None, None, None]:
    reload_models()
    yield
    reload_models()


def test_route_prefers_explicit_user_model() -> None:
    tool_models = json.dumps([
        {
            "id": "tool-primary",
            "model": "provider/tool-primary",
            "api_key": "sk-tool",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_TOOL_MODELS": tool_models, "LLM_DEFAULT_MODEL": "tool-primary"},
        clear=False,
    ):
        reload_models()
        model_id = route_chat_model(
            requested_model="tool-primary",
            thread_model="some-thread-model",
        )
        assert model_id == "tool-primary"


def test_route_uses_thread_model_when_request_not_specified() -> None:
    tool_models = json.dumps([
        {
            "id": "tool-primary",
            "model": "provider/tool-primary",
            "api_key": "sk-tool",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_TOOL_MODELS": tool_models, "LLM_DEFAULT_MODEL": "tool-primary"},
        clear=False,
    ):
        reload_models()
        model_id = route_chat_model(
            requested_model=None,
            thread_model="tool-primary",
        )
        assert model_id == "tool-primary"


def test_route_ignores_utility_model_for_chat_selection() -> None:
    tool_models = json.dumps([
        {
            "id": "tool-primary",
            "model": "provider/tool-primary",
            "api_key": "sk-tool",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    utility_models = json.dumps([
        {
            "id": "qwen-flash",
            "model": "qwen-flash",
            "api_key": "sk-util",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {
            "LLM_TOOL_MODELS": tool_models,
            "LLM_UTILITY_MODELS": utility_models,
            "LLM_DEFAULT_MODEL": "tool-primary",
        },
        clear=False,
    ):
        reload_models()
        model_id = route_chat_model(requested_model="qwen-flash")
        assert model_id == "tool-primary"


def test_validate_requested_model_rejects_unknown_model() -> None:
    tool_models = json.dumps([
        {
            "id": "tool-primary",
            "model": "provider/tool-primary",
            "api_key": "sk-tool",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_TOOL_MODELS": tool_models, "LLM_DEFAULT_MODEL": "tool-primary"},
        clear=False,
    ):
        reload_models()
        with pytest.raises(InvalidRequestedModelError, match="Unknown model id"):
            validate_requested_model("missing-model", allowed_categories=("tool", "gen"))


def test_validate_requested_model_rejects_disallowed_category() -> None:
    tool_models = json.dumps([
        {
            "id": "tool-primary",
            "model": "provider/tool-primary",
            "api_key": "sk-tool",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    utility_models = json.dumps([
        {
            "id": "qwen-flash",
            "model": "qwen-flash",
            "api_key": "sk-util",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {
            "LLM_TOOL_MODELS": tool_models,
            "LLM_UTILITY_MODELS": utility_models,
            "LLM_DEFAULT_MODEL": "tool-primary",
        },
        clear=False,
    ):
        reload_models()
        with pytest.raises(InvalidRequestedModelError, match="not allowed"):
            validate_requested_model("qwen-flash", allowed_categories=("tool", "gen"))


def test_route_picks_first_tool_capable_candidate_when_no_selection() -> None:
    tool_models = json.dumps([
        {
            "id": "tool-best",
            "model": "provider/tool-best",
            "api_key": "sk-tool",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    gen_models = json.dumps([
        {
            "id": "gen-fallback",
            "model": "provider/gen-fallback",
            "api_key": "sk-gen",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {
            "LLM_TOOL_MODELS": tool_models,
            "LLM_GEN_MODELS": gen_models,
            "LLM_DEFAULT_MODEL": "gen-fallback",
        },
        clear=False,
    ):
        reload_models()
        model_id = route_chat_model(requested_model=None, thread_model=None, require_tools=True)
        assert model_id == "tool-best"


def test_route_falls_back_to_default_when_no_tool_capable_models() -> None:
    gen_models = json.dumps([
        {
            "id": "gen-default",
            "model": "provider/gen-default",
            "api_key": "sk-gen",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {"LLM_GEN_MODELS": gen_models, "LLM_DEFAULT_MODEL": "gen-default"},
        clear=False,
    ):
        reload_models()
        model_id = route_chat_model(requested_model=None, thread_model=None, require_tools=True)
        assert model_id == "gen-default"


def test_route_writing_prefers_generation_category() -> None:
    tool_models = json.dumps([
        {
            "id": "tool-primary",
            "model": "provider/tool-primary",
            "api_key": "sk-tool",
            "base_url": "https://example.com/v1",
            "supports_tools": True,
        }
    ])
    gen_models = json.dumps([
        {
            "id": "deepseek-v3.2",
            "model": "provider/deepseek-v3.2",
            "api_key": "sk-gen",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {
            "LLM_TOOL_MODELS": tool_models,
            "LLM_GEN_MODELS": gen_models,
            "LLM_DEFAULT_MODEL": "tool-primary",
        },
        clear=False,
    ):
        reload_models()
        model_id = route_writing_model()
        assert model_id == "deepseek-v3.2"


def test_list_user_selectable_models_hides_utility_by_default() -> None:
    tool_models = json.dumps([
        {
            "id": "tool-primary",
            "model": "provider/tool-primary",
            "api_key": "sk-tool",
            "base_url": "https://example.com/v1",
        }
    ])
    gen_models = json.dumps([
        {
            "id": "gen-primary",
            "model": "provider/gen-primary",
            "api_key": "sk-gen",
            "base_url": "https://example.com/v1",
        }
    ])
    utility_models = json.dumps([
        {
            "id": "qwen-flash",
            "model": "qwen-flash",
            "api_key": "sk-util",
            "base_url": "https://example.com/v1",
        }
    ])
    with patch.dict(
        os.environ,
        {
            "LLM_TOOL_MODELS": tool_models,
            "LLM_GEN_MODELS": gen_models,
            "LLM_UTILITY_MODELS": utility_models,
        },
        clear=False,
    ):
        reload_models()
        selectable = list_user_selectable_models(purpose="chat")
        selectable_ids = [model.id for model in selectable]
        assert "tool-primary" in selectable_ids
        assert "gen-primary" in selectable_ids
        assert "qwen-flash" not in selectable_ids
