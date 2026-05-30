"""Gateway facade for the DataService-owned model catalog."""

from __future__ import annotations

from typing import Any, Literal

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.model_catalog import (
    ModelCatalogCreatePayload,
    ModelCatalogHealthPayload,
    ModelCatalogPayload,
    ModelCatalogUpdatePayload,
)

ModelPurpose = Literal["chat", "writing", "image", "all"]


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
        return await self.dataservice.create_model_catalog_model(ModelCatalogCreatePayload.model_validate(payload))

    async def update_model(
        self,
        model_id: str,
        data: dict[str, Any],
        *,
        admin_id: str,
    ) -> ModelCatalogPayload | None:
        payload = {key: value for key, value in data.items() if value is not None}
        if not str(payload.get("api_key") or "").strip():
            payload.pop("api_key", None)
        payload["admin_id"] = admin_id
        return await self.dataservice.update_model_catalog_model(
            model_id,
            ModelCatalogUpdatePayload.model_validate(payload),
        )

    async def disable_model(self, model_id: str, *, admin_id: str) -> ModelCatalogPayload | None:
        return await self.update_model(model_id, {"enabled": False}, admin_id=admin_id)

    async def set_default_model(self, model_id: str, *, admin_id: str) -> ModelCatalogPayload | None:
        return await self.dataservice.set_model_catalog_default(model_id, admin_id=admin_id)

    async def test_model(self, model_id: str) -> ModelCatalogPayload | None:
        return await self.dataservice.update_model_catalog_health(
            model_id,
            ModelCatalogHealthPayload(status="healthy"),
        )

    async def list_public_models(self, *, purpose: ModelPurpose = "chat") -> list[ModelCatalogPayload]:
        category = _purpose_category(purpose)
        return await self.dataservice.list_model_catalog_models(
            category=category,
            enabled_only=True,
        )


def _purpose_category(purpose: str) -> str | None:
    if purpose == "all":
        return None
    if purpose == "image":
        return "image"
    return "llm"
