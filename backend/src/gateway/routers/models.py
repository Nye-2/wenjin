"""Models router for LLM model management."""


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ModelInfo(BaseModel):
    """Model information response."""
    name: str
    display_name: str
    provider: str
    max_tokens: int
    supports_thinking: bool
    supports_vision: bool


class ModelsListResponse(BaseModel):
    """List of available models."""
    models: list[ModelInfo]


# Available models
AVAILABLE_MODELS = [
    ModelInfo(
        name="gpt-4o",
        display_name="GPT-4o",
        provider="OpenAI",
        max_tokens=4096,
        supports_thinking=False,
        supports_vision=True,
    ),
    ModelInfo(
        name="gpt-4o-mini",
        display_name="GPT-4o Mini",
        provider="OpenAI",
        max_tokens=4096,
        supports_thinking=False,
        supports_vision=True,
    ),
    ModelInfo(
        name="claude-sonnet-4",
        display_name="Claude Sonnet 4",
        provider="Anthropic",
        max_tokens=4096,
        supports_thinking=True,
        supports_vision=True,
    ),
    ModelInfo(
        name="deepseek-v3",
        display_name="DeepSeek V3",
        provider="DeepSeek",
        max_tokens=4096,
        supports_thinking=False,
        supports_vision=False,
    ),
]


@router.get("/models", response_model=ModelsListResponse)
async def list_models():
    """List all available models."""
    return ModelsListResponse(models=AVAILABLE_MODELS)


@router.get("/models/{model_name}", response_model=ModelInfo)
async def get_model(model_name: str):
    """Get details of a specific model."""
    for model in AVAILABLE_MODELS:
        if model.name == model_name:
            return model
    raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
