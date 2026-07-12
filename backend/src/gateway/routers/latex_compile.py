"""LaTeX compile endpoints."""

from __future__ import annotations

import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.contracts.latex import LatexCompileRequest, LatexCompileResponse
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers.latex_helpers import _not_found
from src.services.latex import LatexCompileService, LatexProjectService
from src.services.references import SourceBibliographyService

router = APIRouter(prefix="/prism/latex-adapter", tags=["latex"])


@router.post("/projects/{project_id}/compile", response_model=LatexCompileResponse)
async def compile_project(
    project_id: str,
    request: LatexCompileRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> LatexCompileResponse:
    project_service = LatexProjectService(dataservice=dataservice)
    project = await project_service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()
    main_file = request.main_file or project.main_file
    workspace_id = _workspace_id_for_project(project)
    if workspace_id:
        try:
            latex_content = project_service.read_text_file(project, main_file)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        validation = await SourceBibliographyService(dataservice=dataservice).validate_citations(
            workspace_id=workspace_id,
            latex_content=latex_content,
        )
        if not validation.get("valid", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Citation validation failed before compile",
                    **validation,
                },
            )
    compile_service = LatexCompileService(dataservice=dataservice)
    try:
        payload = await compile_service.compile_project(
            project,
            main_file=main_file,
            engine=request.engine,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return LatexCompileResponse.model_validate(payload)


def _workspace_id_for_project(project: object) -> str | None:
    workspace_id = getattr(project, "workspace_id", None)
    if workspace_id:
        return str(workspace_id)
    llm_config = getattr(project, "llm_config", None)
    if isinstance(llm_config, dict):
        value = llm_config.get("workspace_id")
        if value:
            return str(value)
    return None


@router.get("/projects/{project_id}/compile/{history_id}/pdf")
async def get_compiled_pdf(
    project_id: str,
    history_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> FileResponse:
    project_service = LatexProjectService(dataservice=dataservice)
    project = await project_service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    compile_service = LatexCompileService(dataservice=dataservice)
    pdf_path = await compile_service.get_history_pdf(
        history_id=history_id,
        project_id=project_id,
    )
    if pdf_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compiled PDF not found")

    media_type = mimetypes.guess_type(pdf_path.name)[0] or "application/pdf"
    encoded_filename = quote(pdf_path.name)
    return FileResponse(
        path=pdf_path,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"},
    )


@router.get("/projects/{project_id}/compile/{history_id}/synctex")
async def get_compiled_synctex(
    project_id: str,
    history_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> FileResponse:
    project_service = LatexProjectService(dataservice=dataservice)
    project = await project_service.get_owned(project_id, str(current_user.id))
    if project is None:
        raise _not_found()

    compile_service = LatexCompileService(dataservice=dataservice)
    synctex_path = await compile_service.get_history_synctex(
        history_id=history_id,
        project_id=project_id,
    )
    if synctex_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Synctex file not found")

    media_type = mimetypes.guess_type(synctex_path.name)[0] or "application/gzip"
    encoded_filename = quote(synctex_path.name)
    return FileResponse(
        path=synctex_path,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )
