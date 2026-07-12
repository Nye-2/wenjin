"""Models router for LLM model discovery."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.model_catalog import ModelCatalogPayload
from src.gateway.deps.core import get_dataservice_client
from src.models.capability_profile import assess_profile_freshness
from src.services.model_catalog_service import ModelCatalogService, ModelPurpose

router = APIRouter()


class ModelInfo(BaseModel):
    """Model information response."""

    name: str
    display_name: str
    category: str
    provider: str
    max_tokens: int
    generation_api: str | None
    capability_profile_version: str
    strict_tool_calls: bool
    streaming: bool
    reasoning_efforts: list[str]
    vision: bool
    native_web_search: bool
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

    freshness = assess_profile_freshness(
        model.capability_profile,
        model.capability_probe,
        model_id=model.model_id,
        model_name=model.model_name,
        base_url=model.base_url,
        generation_api=model.generation_api,
    )
    profile = model.capability_profile
    return ModelInfo(
        name=model.model_id,
        display_name=display_name,
        category=model.category,
        provider=model.provider_name,
        max_tokens=model.max_tokens,
        generation_api=(model.generation_api.value if model.generation_api else None),
        capability_profile_version=profile.profile_version,
        strict_tool_calls=freshness.current and profile.has_strict_tools(),
        streaming=freshness.current and profile.streaming,
        reasoning_efforts=[effort.value for effort in profile.reasoning_efforts] if freshness.current else [],
        vision=freshness.current and profile.vision,
        native_web_search=freshness.current and profile.native_web_search,
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
