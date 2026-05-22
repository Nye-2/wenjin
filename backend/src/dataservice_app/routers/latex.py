"""LaTeX adapter endpoints for DataService internal API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.latex_api import LatexDataService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.latex import (
    LatexCompileHistoryCreatePayload,
    LatexProjectAttachWorkspacePayload,
    LatexProjectCreatePayload,
    LatexProjectTouchPayload,
    LatexProjectUpdatePayload,
)

router = APIRouter(
    prefix="/internal/v1/latex",
    tags=["latex"],
    dependencies=[Depends(require_internal_token)],
)


def _project_payload(project: Any) -> dict[str, Any] | None:
    if project is None:
        return None
    return {
        "id": str(project.id),
        "user_id": str(project.user_id),
        "name": project.name,
        "template_id": project.template_id,
        "main_file": project.main_file,
        "tags": list(project.tags or []),
        "archived": bool(project.archived),
        "trashed": bool(project.trashed),
        "trashed_at": project.trashed_at,
        "file_order": project.file_order or {},
        "llm_config": project.llm_config,
        "workspace_id": project.workspace_id,
        "surface_role": project.surface_role,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _template_payload(template: Any) -> dict[str, Any] | None:
    if template is None:
        return None
    return {
        "id": str(template.id),
        "label": template.label,
        "main_file": template.main_file,
        "category": template.category,
        "description": template.description,
        "description_en": template.description_en,
        "tags": list(template.tags or []),
        "author": template.author,
        "featured": bool(template.featured),
        "template_path": template.template_path,
    }


def _compile_history_payload(history: Any) -> dict[str, Any] | None:
    if history is None:
        return None
    return {
        "id": str(history.id),
        "project_id": str(history.project_id),
        "engine": history.engine,
        "main_file": history.main_file,
        "status": history.status,
        "log": history.log,
        "pdf_path": history.pdf_path,
        "created_at": history.created_at,
    }


@router.get("/projects")
async def list_projects_by_user(
    user_id: str,
    include_trashed: bool = Query(default=False),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    projects = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).list_projects_by_user(user_id, include_trashed=include_trashed)
    return envelope_ok([_project_payload(project) for project in projects])


@router.post("/projects")
async def create_project(
    payload: LatexProjectCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    project = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).create_project(**payload.model_dump())
    await uow.commit()
    return envelope_ok(_project_payload(project))


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    project = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).get_project(project_id)
    return envelope_ok(_project_payload(project))


@router.get("/projects/{project_id}/owned")
async def get_owned_project(
    project_id: str,
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    project = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).get_owned_project(project_id=project_id, user_id=user_id)
    return envelope_ok(_project_payload(project))


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: str,
    payload: LatexProjectUpdatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = LatexDataService(uow.required_session, autocommit=False)
    project = await service.get_project(project_id)
    if project is None:
        return envelope_ok(None)
    updated = await service.update_project(project, **payload.model_dump(exclude_unset=True))
    await uow.commit()
    return envelope_ok(_project_payload(updated))


@router.patch("/projects/{project_id}/touch")
async def touch_project(
    project_id: str,
    payload: LatexProjectTouchPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = LatexDataService(uow.required_session, autocommit=False)
    project = await service.get_project(project_id)
    if project is None:
        return envelope_ok(None)
    touched = await service.touch_project(project, **payload.model_dump(exclude_unset=True))
    await uow.commit()
    return envelope_ok(_project_payload(touched))


@router.post("/projects/{project_id}/attach-workspace")
async def attach_workspace_project(
    project_id: str,
    payload: LatexProjectAttachWorkspacePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = LatexDataService(uow.required_session, autocommit=False)
    project = await service.get_project(project_id)
    if project is None:
        return envelope_ok(None)
    attached = await service.attach_workspace_project(project, workspace_id=payload.workspace_id)
    await uow.commit()
    return envelope_ok(_project_payload(attached))


@router.post("/projects/{project_id}/soft-delete")
async def soft_delete_project(
    project_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = LatexDataService(uow.required_session, autocommit=False)
    project = await service.get_project(project_id)
    if project is None:
        return envelope_ok(None)
    deleted = await service.soft_delete_project(project)
    await uow.commit()
    return envelope_ok(_project_payload(deleted))


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = LatexDataService(uow.required_session, autocommit=False)
    project = await service.get_project(project_id)
    if project is None:
        return envelope_ok({"deleted": False})
    await service.delete_project(project)
    await uow.commit()
    return envelope_ok({"deleted": True})


@router.get("/workspaces/{workspace_id}/primary-project")
async def get_workspace_primary_project(
    workspace_id: str,
    owner_user_id: str,
    template: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    project = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).get_workspace_primary_project(
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        template=template,
    )
    return envelope_ok(_project_payload(project))


@router.get("/binding-integrity")
async def get_latex_binding_integrity_report(
    user_id: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    params: dict[str, Any] = {"surface_role": "primary_manuscript"}
    user_filter = ""
    if user_id is not None:
        params["user_id"] = user_id
        user_filter = "where w.user_id = :user_id"

    result = await uow.required_session.execute(
        text(
            f"""
            select
                w.id as workspace_id,
                w.user_id as user_id,
                w.name as workspace_name,
                count(lp.id) as primary_count
            from workspaces w
            left join latex_projects lp
              on lp.workspace_id = w.id
             and lp.surface_role = :surface_role
            {user_filter}
            group by w.id, w.user_id, w.name
            having count(lp.id) = 0 or count(lp.id) > 1
            order by w.id
            """
        ),
        params,
    )
    missing_primary: list[dict[str, Any]] = []
    duplicate_primary: list[dict[str, Any]] = []
    for row in result.mappings():
        item = {
            "workspace_id": str(row["workspace_id"]),
            "user_id": str(row["user_id"]),
            "workspace_name": str(row["workspace_name"] or ""),
            "primary_count": int(row["primary_count"] or 0),
        }
        if item["primary_count"] == 0:
            missing_primary.append(item)
        else:
            duplicate_primary.append(item)
    return envelope_ok(
        {
            "missing_primary": missing_primary,
            "duplicate_primary": duplicate_primary,
        }
    )


@router.get("/templates")
async def list_templates(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    templates = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).list_templates()
    await uow.commit()
    return envelope_ok([_template_payload(template) for template in templates])


@router.post("/templates/ensure-defaults")
async def ensure_default_templates(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).ensure_default_templates()
    await uow.commit()
    return envelope_ok({"ensured": True})


@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    template = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).get_template(template_id)
    return envelope_ok(_template_payload(template))


@router.post("/compile-history")
async def record_compile_history(
    payload: LatexCompileHistoryCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    history = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).record_compile_history(**payload.model_dump())
    await uow.commit()
    return envelope_ok(_compile_history_payload(history))


@router.get("/compile-history/{history_id}")
async def get_compile_history(
    history_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    history = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).get_compile_history(history_id)
    return envelope_ok(_compile_history_payload(history))


@router.delete("/compile-history/{history_id}")
async def delete_compile_history(
    history_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = LatexDataService(uow.required_session, autocommit=False)
    history = await service.get_compile_history(history_id)
    if history is None:
        return envelope_ok({"deleted": False})
    await service.delete_compile_histories([history])
    await uow.commit()
    return envelope_ok({"deleted": True})


@router.get("/projects/{project_id}/compile-history")
async def list_compile_history(
    project_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    histories = await LatexDataService(
        uow.required_session,
        autocommit=False,
    ).list_compile_history(project_id)
    return envelope_ok([_compile_history_payload(history) for history in histories])
