"""Admin model catalog management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.errors import DataServiceClientError
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_admin
from src.gateway.deps.core import get_dataservice_client
from src.gateway.error_mapping import dataservice_client_to_http_exception
from src.services.model_catalog_service import ModelCatalogService

router = APIRouter(prefix="/admin/models", tags=["admin", "models"])


async def _service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ModelCatalogService:
    return ModelCatalogService(dataservice=dataservice)


def _to_dict(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


@router.get("")
async def list_models(
    category: str | None = None,
    enabled_only: bool = False,
    service: ModelCatalogService = Depends(_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        models = await service.list_models(category=category, enabled_only=enabled_only)
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    return {"items": [_to_dict(model) for model in models], "total": len(models)}


@router.post("")
async def create_model(
    payload: dict[str, Any] = Body(...),
    service: ModelCatalogService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        model = await service.create_model(payload, admin_id=admin.id)
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _to_dict(model)


@router.patch("/{model_id}")
async def update_model(
    model_id: str,
    payload: dict[str, Any] = Body(...),
    service: ModelCatalogService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any] | None:
    try:
        model = await service.update_model(model_id, payload, admin_id=admin.id)
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _to_dict(model) if model else None


@router.post("/{model_id}/disable")
async def disable_model(
    model_id: str,
    service: ModelCatalogService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any] | None:
    try:
        model = await service.disable_model(model_id, admin_id=admin.id)
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _to_dict(model) if model else None


@router.post("/{model_id}/set-default")
async def set_default_model(
    model_id: str,
    service: ModelCatalogService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any] | None:
    try:
        model = await service.set_default_model(model_id, admin_id=admin.id)
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _to_dict(model) if model else None


@router.post("/{model_id}/test")
async def test_model(
    model_id: str,
    service: ModelCatalogService = Depends(_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any] | None:
    try:
        model = await service.test_model(model_id)
    except DataServiceClientError as exc:
        raise dataservice_client_to_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _to_dict(model) if model else None
