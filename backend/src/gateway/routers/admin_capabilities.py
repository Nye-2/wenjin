"""Admin capability management endpoints."""

from __future__ import annotations

import io
import zipfile
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_admin
from src.gateway.deps.core import get_dataservice_client
from src.services.admin_capability_service import AdminCapabilityService

router = APIRouter(prefix="/admin/capabilities", tags=["admin", "capabilities"])


async def _service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> AdminCapabilityService:
    from src.academic.cache.redis_client import redis_client
    from src.services.event_bus import EventBus

    if redis_client._client is None:
        await redis_client.connect()
    yield AdminCapabilityService(
        event_bus=EventBus(redis_client.client),
        dataservice=dataservice,
    )


def _to_dict(cap) -> dict[str, Any]:
    return {
        "id": cap.id,
        "workspace_type": cap.workspace_type,
        "enabled": cap.enabled,
        "display_name": cap.display_name,
        "description": cap.description,
        "intent_description": cap.intent_description,
        "trigger_phrases": cap.trigger_phrases,
        "required_decisions": cap.required_decisions,
        "brief_schema": cap.brief_schema,
        "graph_template": cap.graph_template,
        "ui_meta": cap.ui_meta,
        "runtime": cap.runtime,
        "dashboard_meta": cap.dashboard_meta,
        "notes": cap.notes,
    }


@router.get("")
async def list_capabilities(
    service: AdminCapabilityService = Depends(_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    items = await service.list_all()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for cap in items:
        grouped.setdefault(cap.workspace_type, []).append(_to_dict(cap))
    return {"groups": grouped, "total": len(items)}


@router.get("/export")
async def export_zip(
    service: AdminCapabilityService = Depends(_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> Response:
    items = await service.list_all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for cap in items:
            path = f"capabilities/{cap.workspace_type}/{cap.id}.yaml"
            zf.writestr(path, service.to_yaml_text(cap))
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="capabilities.zip"'},
    )


@router.get("/{capability_id}")
async def get_capability(
    capability_id: str,
    workspace_type: str,
    service: AdminCapabilityService = Depends(_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    cap = await service.get(capability_id, workspace_type)
    if cap is None:
        raise HTTPException(404, "capability not found")
    return {
        "yaml": service.to_yaml_text(cap),
        "updated_at": getattr(cap, "updated_at", None),
    }


@router.post("/validate")
async def validate_capability(
    payload: dict = Body(...),
    service: AdminCapabilityService = Depends(_service),
    _admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    errors = await service.validate(payload.get("yaml", ""))
    return {"valid": not errors, "errors": errors}


@router.post("")
async def create_capability(
    payload: dict = Body(...),
    service: AdminCapabilityService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        cap = await service.create(yaml_text=payload["yaml"], admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(cap)


@router.put("/{capability_id}")
async def update_capability(
    capability_id: str,
    workspace_type: str,
    payload: dict = Body(...),
    service: AdminCapabilityService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        cap = await service.update(
            capability_id=capability_id,
            workspace_type=workspace_type,
            yaml_text=payload["yaml"],
            admin_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(cap)


@router.delete("/{capability_id}")
async def delete_capability(
    capability_id: str,
    workspace_type: str,
    service: AdminCapabilityService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> Response:
    try:
        await service.delete(capability_id, workspace_type, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{capability_id}/toggle")
async def toggle_capability(
    capability_id: str,
    workspace_type: str,
    service: AdminCapabilityService = Depends(_service),
    admin: AccountAuthSubject = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        cap = await service.toggle(
            capability_id, workspace_type, admin_id=admin.id
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _to_dict(cap)


@router.post("/import-from-seed")
async def import_from_seed(
    _admin: AccountAuthSubject = Depends(get_current_admin),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    from src.services.capability_loader import DEFAULT_SEED_DIR, CapabilityLoader

    loader = CapabilityLoader(seed_dir=DEFAULT_SEED_DIR, dataservice=dataservice)
    loaded = await loader.load_all(overwrite=True)
    return {
        "loaded": [
            {"id": c.id, "workspace_type": c.workspace_type} for c in loaded
        ]
    }
