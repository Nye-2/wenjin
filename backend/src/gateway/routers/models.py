"""Models router for LLM model discovery."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import get_default_model_id
from src.config.llm_config import ModelConfig
from src.models import (
    get_model_category,
    list_user_selectable_models,
    model_supports_reasoning_effort,
    model_supports_thinking,
    model_supports_vision,
)

router = APIRouter()


class ModelInfo(BaseModel):
    """Model information response."""

    name: str
    display_name: str
    category: str
    provider: str
    max_tokens: int
    supports_tools: bool
    supports_thinking: bool
    supports_reasoning_effort: bool
    supports_vision: bool
    is_default: bool


class ModelsListResponse(BaseModel):
    """List of available models."""

    models: list[ModelInfo]


def _infer_provider(model: ModelConfig) -> str:
    """Infer provider label from model metadata."""
    base_url = (model.base_url or "").lower()
    raw_model = (model.model or "").lower()

    if "anthropic" in base_url or raw_model.startswith("claude"):
        return "Anthropic"
    if "dashscope" in base_url or raw_model.startswith("qwen"):
        return "Qwen"
    if "bigmodel" in base_url or "glm" in raw_model:
        return "Zhipu"
    if "deepseek" in raw_model:
        return "DeepSeek"
    if "qnaigc" in base_url:
        return "QNAIGC"
    if "deepseek" in base_url or "deepseek" in raw_model:
        return "DeepSeek"
    if "openai" in base_url:
        return "OpenAI-Compatible"
    return "Custom"


def _supports_vision(model: ModelConfig) -> bool:
    return model_supports_vision(model.id)


def _to_model_info(model: ModelConfig, *, category: str, mark_default: bool) -> ModelInfo:
    display_name = model.name or model.id
    if mark_default:
        display_name = f"{display_name} (Default)"

    return ModelInfo(
        name=model.id,
        display_name=display_name,
        category=category,
        provider=_infer_provider(model),
        max_tokens=model.max_tokens,
        supports_tools=model.supports_tools,
        supports_thinking=model_supports_thinking(model.id),
        supports_reasoning_effort=model_supports_reasoning_effort(model.id),
        supports_vision=_supports_vision(model),
        is_default=mark_default,
    )


def _collect_models(purpose: Literal["chat", "writing", "image", "all"] = "chat") -> list[ModelInfo]:
    selectable = list_user_selectable_models(purpose=purpose)
    default_model: str | None
    try:
        default_model = get_default_model_id()
    except Exception:
        default_model = None

    models: list[ModelInfo] = []
    for model in selectable:
        category = get_model_category(model.id) or "custom"
        models.append(
            _to_model_info(
                model,
                category=category,
                mark_default=(model.id == default_model),
            )
        )
    return models


@router.get("/models", response_model=ModelsListResponse)
async def list_models(
    purpose: Literal["chat", "writing", "image", "all"] = "chat",
) -> ModelsListResponse:
    """List user-selectable models for a specific purpose."""
    return ModelsListResponse(models=_collect_models(purpose=purpose))


@router.get("/models/{model_name}", response_model=ModelInfo)
async def get_model(
    model_name: str,
    purpose: Literal["chat", "writing", "image", "all"] = "chat",
) -> ModelInfo:
    """Get details of a specific model by id."""
    for model in _collect_models(purpose=purpose):
        if model.name == model_name:
            return model
    raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
