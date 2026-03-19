"""Academic router for paper and artifact management.

Note: Workspace CRUD operations are handled in workspaces.py.
This router handles paper and artifact operations within workspaces.
"""

from fastapi import APIRouter, Depends, File, Form, UploadFile

from src.application.errors import ApplicationError
from src.application.handlers.academic_compat_handler import AcademicCompatHandler
from src.database import User
from src.gateway.access_control import (
    owner_check_session_from_service as _owner_check_session_from_service,
)
from src.gateway.access_control import (
    require_workspace_owner,
    require_workspace_owner_by_session as _require_workspace_owner,
)
from src.gateway.auth_dependencies import get_current_user
from src.gateway.contracts.artifact import (
    ArtifactResponse,
    ArtifactsListResponse,
    artifact_to_response,
    artifact_to_responses,
)
from src.gateway.contracts.paper import (
    PaperSummaryResponse as PaperResponse,
)
from src.gateway.contracts.paper import (
    paper_to_summary_response,
)
from src.gateway.deps import get_artifact_service, get_db, get_paper_service, get_workspace_service
from src.gateway.error_mapping import to_http_exception
from src.gateway.resource_access import (
    ensure_workspace_owner_for_service as _shared_ensure_workspace_owner_for_service,
)
from src.gateway.resource_access import (
    get_workspace_artifact_or_404 as _shared_get_workspace_artifact_or_404,
)
from src.gateway.validators.artifact import ArtifactCreatePayloadValidator as ArtifactCreate
from src.gateway.validators.paper import PaperCreatePayloadValidator as PaperCreate

router = APIRouter(tags=["academic"])
__all__ = ["get_artifact_service", "get_db", "get_paper_service", "router"]


async def get_academic_compat_handler(
    paper_service=Depends(get_paper_service),
    artifact_service=Depends(get_artifact_service),
) -> AcademicCompatHandler:
    """Get deprecated academic compatibility handler."""
    return AcademicCompatHandler(
        paper_service=paper_service,
        artifact_service=artifact_service,
    )


# ============ Paper Endpoints ============

@router.post("/academic/papers", response_model=PaperResponse, status_code=201)
async def create_paper(
    request: PaperCreate,
    current_user: User = Depends(get_current_user),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """Create a new paper via the deprecated academic compatibility surface."""
    try:
        paper = await handler.create_paper(request)
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return paper_to_summary_response(paper)


@router.post("/papers/upload")
async def upload_paper(
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    workspace_service=Depends(get_workspace_service),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """Upload a new paper (PDF).

    Validates the file is a PDF, saves metadata as a paper record,
    and returns structured response with paper_id.
    """
    await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )

    try:
        return await handler.upload_paper(file=file, workspace_id=workspace_id)
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc


@router.get("/papers/search")
async def search_papers(
    query: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """Search papers in Semantic Scholar."""
    try:
        return await handler.search_papers(query=query, limit=limit)
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc


# ============ Artifact Endpoints ============

@router.get("/workspaces/{workspace_id}/artifacts", response_model=ArtifactsListResponse)
async def list_artifacts(
    workspace_id: str,
    artifact_type: str | None = None,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """List artifacts in a workspace."""
    await _shared_ensure_workspace_owner_for_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    try:
        artifacts = await handler.list_artifacts(
            workspace_id=workspace_id,
            artifact_type=artifact_type,
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return ArtifactsListResponse(
        artifacts=artifact_to_responses(artifacts),
        count=len(artifacts),
    )


@router.post("/workspaces/{workspace_id}/artifacts", response_model=ArtifactResponse, status_code=201)
async def create_artifact(
    workspace_id: str,
    request: ArtifactCreate,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """Create a new artifact."""
    await _shared_ensure_workspace_owner_for_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    try:
        artifact = await handler.create_artifact(
            workspace_id=workspace_id,
            request=request,
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return artifact_to_response(artifact)


@router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """Get artifact details."""
    await _shared_ensure_workspace_owner_for_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )
    artifact = await _shared_get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )
    return artifact_to_response(artifact)


@router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}/lineage")
async def get_artifact_lineage(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service = Depends(get_artifact_service),
    handler: AcademicCompatHandler = Depends(get_academic_compat_handler),
):
    """Get artifact lineage (parent chain)."""
    await _shared_ensure_workspace_owner_for_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )
    await _shared_get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    try:
        lineage = await handler.get_artifact_lineage(artifact_id)
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc
    return {
        "lineage": artifact_to_responses(lineage),
    }
