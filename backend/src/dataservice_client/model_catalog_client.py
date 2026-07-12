"""ModelCatalog DataService client methods."""

from __future__ import annotations

from typing import Any

from src.dataservice_client.contracts.model_catalog import (
    ModelCapabilityAssessmentPayload,
    ModelCatalogCreatePayload,
    ModelCatalogHealthPayload,
    ModelCatalogPayload,
    ModelCatalogUpdatePayload,
    ModelRuntimeConfigPayload,
)


class ModelCatalogDataServiceClientMixin:
    """Typed DataService methods for this domain."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def list_model_catalog_models(
        self,
        *,
        category: str | None = None,
        enabled_only: bool = False,
    ) -> list[ModelCatalogPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/model-catalog/models",
            params={"category": category, "enabled_only": enabled_only},
        )
        return [ModelCatalogPayload.model_validate(item) for item in payload["data"]]

    async def get_model_catalog_model(self, model_id: str) -> ModelCatalogPayload | None:
        payload = await self._request("GET", f"/internal/v1/model-catalog/models/{model_id}")
        data = payload.get("data")
        return ModelCatalogPayload.model_validate(data) if data is not None else None

    async def get_model_catalog_runtime_model(
        self,
        model_id: str,
    ) -> ModelRuntimeConfigPayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/model-catalog/models/{model_id}/runtime",
        )
        data = payload.get("data")
        return ModelRuntimeConfigPayload.model_validate(data) if data is not None else None

    async def create_model_catalog_model(self, command: ModelCatalogCreatePayload) -> ModelCatalogPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/model-catalog/models",
            json=command.model_dump(mode="json"),
        )
        return ModelCatalogPayload.model_validate(payload["data"])

    async def update_model_catalog_model(
        self,
        model_id: str,
        command: ModelCatalogUpdatePayload,
    ) -> ModelCatalogPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/model-catalog/models/{model_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return ModelCatalogPayload.model_validate(data) if data is not None else None

    async def set_model_catalog_default(self, model_id: str, *, admin_id: str | None = None) -> ModelCatalogPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/model-catalog/models/{model_id}/default",
            json={"admin_id": admin_id},
        )
        data = payload.get("data")
        return ModelCatalogPayload.model_validate(data) if data is not None else None

    async def update_model_catalog_health(
        self,
        model_id: str,
        command: ModelCatalogHealthPayload,
    ) -> ModelCatalogPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/model-catalog/models/{model_id}/health",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return ModelCatalogPayload.model_validate(data) if data is not None else None

    async def update_model_capability_assessment(
        self,
        model_id: str,
        command: ModelCapabilityAssessmentPayload,
    ) -> ModelCatalogPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/model-catalog/models/{model_id}/capability-assessment",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data")
        return ModelCatalogPayload.model_validate(data) if data is not None else None

    async def list_model_catalog_runtime_models(
        self,
        *,
        category: str | None = None,
    ) -> list[ModelRuntimeConfigPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/model-catalog/models/runtime",
            params={"category": category},
        )
        return [ModelRuntimeConfigPayload.model_validate(item) for item in payload["data"]]
