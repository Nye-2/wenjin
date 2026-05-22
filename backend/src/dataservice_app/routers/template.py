"""Workspace template endpoints for DataService internal API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.template_api import TemplateDataService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.template import (
    WorkspaceTemplateCreatePayload,
    WorkspaceTemplateDeactivatePayload,
)

router = APIRouter(
    prefix="/internal/v1/templates",
    tags=["templates"],
    dependencies=[Depends(require_internal_token)],
)


def _template_payload(template: Any) -> dict[str, Any] | None:
    if template is None:
        return None
    return {
        "id": str(template.id),
        "workspace_id": str(template.workspace_id),
        "name": template.name,
        "category": template.category,
        "source_type": template.source_type,
        "source_file_path": template.source_file_path,
        "structure": template.structure or {},
        "format_spec": template.format_spec or {},
        "content_guidelines": template.content_guidelines or {},
        "latex_preamble": template.latex_preamble,
        "is_active": bool(template.is_active),
        "is_builtin": bool(template.is_builtin),
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


@router.get("/workspaces/{workspace_id}/active")
async def get_active_template(
    workspace_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    template = await TemplateDataService(
        uow.required_session,
        autocommit=False,
    ).get_active(workspace_id)
    return envelope_ok(_template_payload(template))


@router.get("/workspaces/{workspace_id}")
async def list_workspace_templates(
    workspace_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    templates = await TemplateDataService(
        uow.required_session,
        autocommit=False,
    ).list_by_workspace(workspace_id)
    return envelope_ok([_template_payload(template) for template in templates])


@router.post("")
async def create_template(
    payload: WorkspaceTemplateCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    template = await TemplateDataService(
        uow.required_session,
        autocommit=False,
    ).create(**payload.model_dump())
    await uow.commit()
    return envelope_ok(_template_payload(template))


@router.post("/workspaces/{workspace_id}/deactivate-active")
async def deactivate_active_templates(
    workspace_id: str,
    payload: WorkspaceTemplateDeactivatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    await TemplateDataService(
        uow.required_session,
        autocommit=False,
    ).deactivate_active_templates(
        workspace_id=workspace_id,
        exclude_template_id=payload.exclude_template_id,
    )
    await uow.commit()
    return envelope_ok({"deactivated": True})


@router.post("/workspaces/{workspace_id}/{template_id}/activate")
async def activate_template(
    workspace_id: str,
    template_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    template = await TemplateDataService(
        uow.required_session,
        autocommit=False,
    ).activate(template_id=template_id, workspace_id=workspace_id)
    await uow.commit()
    return envelope_ok(_template_payload(template))


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    template = await TemplateDataService(
        uow.required_session,
        autocommit=False,
    ).get(template_id)
    return envelope_ok(_template_payload(template))


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    workspace_id: str | None = None,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    deleted = await TemplateDataService(
        uow.required_session,
        autocommit=False,
    ).delete(template_id=template_id, workspace_id=workspace_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted})
