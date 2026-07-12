"""Gateway facade for the DataService-owned model catalog."""

from __future__ import annotations

import logging
from typing import Any, Literal

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.model_catalog import (
    ModelCapabilityAssessmentPayload,
    ModelCatalogCreatePayload,
    ModelCatalogHealthPayload,
    ModelCatalogPayload,
    ModelCatalogUpdatePayload,
)
from src.models.capability_probe import ModelProbeTarget, probe_model_capabilities
from src.models.capability_profile import GenerationAPI
from src.services.model_catalog_cache import refresh_model_catalog_cache

logger = logging.getLogger(__name__)

ModelPurpose = Literal["chat", "writing", "image", "all"]

_CLEARABLE_UPDATE_FIELDS = {
    "pricing_policy_id",
    "timeout_seconds",
    "max_retries",
    "default_headers",
}


class ModelCatalogService:
    """Thin gateway service over model catalog DataService methods."""

    def __init__(self, *, dataservice: AsyncDataServiceClient) -> None:
        self.dataservice = dataservice

    async def list_models(
        self,
        *,
        category: str | None = None,
        enabled_only: bool = False,
    ) -> list[ModelCatalogPayload]:
        return await self.dataservice.list_model_catalog_models(
            category=category,
            enabled_only=enabled_only,
        )

    async def get_model(self, model_id: str) -> ModelCatalogPayload | None:
        return await self.dataservice.get_model_catalog_model(model_id)

    async def create_model(self, data: dict[str, Any], *, admin_id: str) -> ModelCatalogPayload:
        payload = dict(data)
        payload["admin_id"] = admin_id
        record = await self.dataservice.create_model_catalog_model(ModelCatalogCreatePayload.model_validate(payload))
        await self._refresh_runtime_cache_best_effort()
        return record

    async def update_model(
        self,
        model_id: str,
        data: dict[str, Any],
        *,
        admin_id: str,
    ) -> ModelCatalogPayload | None:
        payload = {
            key: value
            for key, value in data.items()
            if value is not None or key in _CLEARABLE_UPDATE_FIELDS
        }
        if not str(payload.get("api_key") or "").strip():
            payload.pop("api_key", None)
        payload["admin_id"] = admin_id
        record = await self.dataservice.update_model_catalog_model(
            model_id,
            ModelCatalogUpdatePayload.model_validate(payload),
        )
        await self._refresh_runtime_cache_best_effort()
        return record

    async def disable_model(self, model_id: str, *, admin_id: str) -> ModelCatalogPayload | None:
        return await self.update_model(model_id, {"enabled": False}, admin_id=admin_id)

    async def set_default_model(self, model_id: str, *, admin_id: str) -> ModelCatalogPayload | None:
        record = await self.dataservice.set_model_catalog_default(model_id, admin_id=admin_id)
        await self._refresh_runtime_cache_best_effort()
        return record

    async def test_model(self, model_id: str) -> ModelCatalogPayload | None:
        try:
            runtime = await self.dataservice.get_model_catalog_runtime_model(model_id)
            if runtime is None:
                return await self.dataservice.update_model_catalog_health(
                    model_id,
                    ModelCatalogHealthPayload(
                        status="failed",
                        error_message="model configuration was not found",
                    ),
                )
            if not runtime.api_key or not runtime.base_url or not runtime.model_name:
                return await self.dataservice.update_model_catalog_health(
                    model_id,
                    ModelCatalogHealthPayload(
                        status="failed",
                        error_message="runtime model configuration is incomplete",
                    ),
                )
            if not isinstance(runtime.generation_api, GenerationAPI):
                return await self.dataservice.update_model_catalog_health(
                    model_id,
                    ModelCatalogHealthPayload(
                        status="failed",
                        error_message="runtime model has no language generation API",
                    ),
                )
            assessment = await probe_model_capabilities(
                ModelProbeTarget(
                    model_id=runtime.model_id,
                    model_name=runtime.model_name,
                    base_url=runtime.base_url,
                    api_key=runtime.api_key,
                    generation_api=runtime.generation_api,
                    default_headers=runtime.default_headers,
                    timeout_seconds=runtime.timeout_seconds or 30.0,
                )
            )
        except Exception as exc:
            return await self.dataservice.update_model_catalog_health(
                model_id,
                ModelCatalogHealthPayload(
                    status="failed",
                    error_message=str(exc),
                ),
            )
        record = await self.dataservice.update_model_capability_assessment(
            model_id,
            ModelCapabilityAssessmentPayload(
                profile=assessment.profile,
                evidence=assessment.evidence,
            ),
        )
        await self._refresh_runtime_cache_best_effort()
        return record

    async def list_public_models(self, *, purpose: ModelPurpose = "chat") -> list[ModelCatalogPayload]:
        category = _purpose_category(purpose)
        return await self.dataservice.list_model_catalog_models(
            category=category,
            enabled_only=True,
        )

    async def _refresh_runtime_cache_best_effort(self) -> None:
        try:
            await refresh_model_catalog_cache(self.dataservice)
        except Exception:
            logger.warning("Model catalog runtime cache refresh failed", exc_info=True)


def _purpose_category(purpose: str) -> str | None:
    if purpose == "all":
        return None
    if purpose == "image":
        return "image"
    return "llm"
