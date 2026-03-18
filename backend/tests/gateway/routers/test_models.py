"""Tests for models discovery router."""

import json
import os
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config.llm_config import reload_models
from src.gateway.routers import models as models_router


def _create_client() -> TestClient:
    app = FastAPI()
    app.include_router(models_router.router)
    return TestClient(app)


def _sample_tool_models() -> str:
    return json.dumps(
        [
            {
                "id": "qwen3.5-plus",
                "name": "Qwen3.5 Plus",
                "model": "qwen3.5-plus",
                "api_key": "sk-tool",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "supports_tools": True,
            },
            {
                "id": "glm-5",
                "name": "GLM-5",
                "model": "z-ai/glm-5",
                "api_key": "sk-tool-2",
                "base_url": "https://api.qnaigc.com/v1",
                "supports_tools": True,
            },
        ]
    )


def _sample_gen_models() -> str:
    return json.dumps(
        [
            {
                "id": "gen-model",
                "name": "Gen Model",
                "model": "provider/gen-model",
                "api_key": "sk-gen",
                "base_url": "https://example.com/v1",
            }
        ]
    )


def _sample_utility_models() -> str:
    return json.dumps(
        [
            {
                "id": "qwen-flash",
                "name": "Qwen Flash",
                "model": "qwen-flash",
                "api_key": "sk-util",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            }
        ]
    )


class TestModelsRouter:
    def setup_method(self):
        reload_models()

    def teardown_method(self):
        reload_models()

    def test_list_models_includes_default_and_capabilities(self):
        with patch.dict(
            os.environ,
            {
                "LLM_TOOL_MODELS": _sample_tool_models(),
                "LLM_GEN_MODELS": _sample_gen_models(),
                "LLM_UTILITY_MODELS": _sample_utility_models(),
                "LLM_DEFAULT_MODEL": "qwen3.5-plus",
            },
            clear=False,
        ):
            reload_models()
            client = _create_client()
            response = client.get("/models")

        assert response.status_code == 200
        payload = response.json()
        assert "models" in payload
        assert len(payload["models"]) >= 2
        default_entry = next(
            model for model in payload["models"] if model["name"] == "qwen3.5-plus"
        )
        assert default_entry["is_default"] is True
        assert default_entry["supports_tools"] is True
        assert default_entry["category"] == "tool"
        model_names = [model["name"] for model in payload["models"]]
        assert "qwen-flash" not in model_names

    def test_get_model_by_id(self):
        with patch.dict(
            os.environ,
            {
                "LLM_TOOL_MODELS": _sample_tool_models(),
                "LLM_DEFAULT_MODEL": "qwen3.5-plus",
            },
            clear=False,
        ):
            reload_models()
            client = _create_client()
            response = client.get("/models/glm-5")

        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "glm-5"
        assert payload["supports_tools"] is True

    def test_list_models_supports_purpose_filter(self):
        image_models = json.dumps(
            [
                {
                    "id": "kling-v2-1",
                    "name": "Kling V2.1",
                    "model": "kling-v2-1",
                    "api_key": "sk-image",
                    "base_url": "https://example.com/v1",
                }
            ]
        )
        with patch.dict(
            os.environ,
            {
                "LLM_TOOL_MODELS": _sample_tool_models(),
                "LLM_GEN_MODELS": _sample_gen_models(),
                "LLM_IMAGE_MODELS": image_models,
                "LLM_DEFAULT_MODEL": "qwen3.5-plus",
            },
            clear=False,
        ):
            reload_models()
            client = _create_client()
            response = client.get("/models?purpose=image")

        assert response.status_code == 200
        payload = response.json()
        assert payload["models"]
        assert all(model["category"] == "image" for model in payload["models"])
