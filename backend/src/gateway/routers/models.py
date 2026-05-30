"""Models router for LLM model discovery."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.model_catalog import ModelCatalogPayload
from src.gateway.deps.core import get_dataservice_client
from src.services.model_catalog_service import ModelCatalogService, ModelPurpose

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


async def _service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ModelCatalogService:
    return ModelCatalogService(dataservice=dataservice)


def _to_model_info(model: ModelCatalogPayload) -> ModelInfo:
    display_name = model.display_name or model.model_id
    if model.is_default:
        display_name = f"{display_name} (Default)"

    return ModelInfo(
        name=model.model_id,
        display_name=display_name,
        category=model.category,
        provider=model.provider_name,
        max_tokens=model.max_tokens,
        supports_tools=model.supports_tools,
        supports_thinking=model.supports_reasoning_effort,
        supports_reasoning_effort=model.supports_reasoning_effort,
        supports_vision=model.supports_vision,
        is_default=model.is_default,
    )


async def _collect_models(
    service: ModelCatalogService,
    *,
    purpose: ModelPurpose = "chat",
) -> list[ModelInfo]:
    return [_to_model_info(model) for model in await service.list_public_models(purpose=purpose)]


@router.get("/models", response_model=ModelsListResponse)
async def list_models(
    purpose: Literal["chat", "writing", "image", "all"] = "chat",
    service: ModelCatalogService = Depends(_service),
) -> ModelsListResponse:
    """List user-selectable models for a specific purpose."""
    return ModelsListResponse(models=await _collect_models(service, purpose=purpose))


@router.get("/models/{model_name}", response_model=ModelInfo)
async def get_model(
    model_name: str,
    purpose: Literal["chat", "writing", "image", "all"] = "chat",
    service: ModelCatalogService = Depends(_service),
) -> ModelInfo:
    """Get details of a specific model by id."""
    for model in await _collect_models(service, purpose=purpose):
        if model.name == model_name:
            return model
    raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
