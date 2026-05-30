"""LaTeX project endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.latex import (
    LatexCreateProjectRequest,
    LatexProjectListResponse,
    LatexProjectResponse,
    LatexUpdateProjectRequest,
)
from src.dataservice_client import AsyncDataServiceClient
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers.latex_helpers import _not_found
from src.services.latex import LatexProjectService
from src.services.latex.project_service import LatexTemplateError, LatexTemplateNotFoundError

router = APIRouter(prefix="/prism/latex-adapter", tags=["latex"])


@router.get("/health")
async def latex_health() -> dict[str, str]:
    """Module health endpoint."""
    return {"status": "ok", "module": "latex"}


@router.get("/projects", response_model=LatexProjectListResponse)
async def list_projects(
    include_trashed: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexProjectListResponse:
    service = LatexProjectService(dataservice=dataservice)
    projects = await service.list_by_user(str(current_user.id), include_trashed=include_trashed)
    return LatexProjectListResponse(projects=projects)  # type: ignore[arg-type]


@router.post("/projects", response_model=LatexProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: LatexCreateProjectRequest,
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexProjectResponse:
    service = LatexProjectService(dataservice=dataservice)
    try:
        project = await service.create(
            user_id=str(current_user.id),
            name=request.name,
            template_id=request.template_id,
        )
    except LatexTemplateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LatexTemplateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return LatexProjectResponse.model_validate(project)


@router.get("/projects/{project_id}", response_model=LatexProjectResponse)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexProjectResponse:
    service = LatexProjectService(dataservice=dataservice)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    return LatexProjectResponse.model_validate(project)


@router.patch("/projects/{project_id}", response_model=LatexProjectResponse)
async def update_project(
    project_id: str,
    request: LatexUpdateProjectRequest,
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexProjectResponse:
    service = LatexProjectService(dataservice=dataservice)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    updated = await service.update(project, **request.model_dump(exclude_unset=True))
    return LatexProjectResponse.model_validate(updated)


@router.delete("/projects/{project_id}")
async def soft_delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, bool]:
    service = LatexProjectService(dataservice=dataservice)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    await service.soft_delete(project)
    return {"ok": True}


@router.delete("/projects/{project_id}/permanent")
async def permanent_delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, bool]:
    service = LatexProjectService(dataservice=dataservice)
    project = await service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    await service.permanent_delete(project)
    return {"ok": True}
