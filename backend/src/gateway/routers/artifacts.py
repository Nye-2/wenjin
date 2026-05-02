"""Artifacts router for artifact management endpoints.

This module provides REST endpoints for:
- Creating artifacts
- Listing artifacts (filtered by workspace and type)
- Getting artifact details
- Updating artifacts
- Deleting artifacts
- Getting artifact lineage (parent chain)
"""

import mimetypes
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from src.academic.services import ArtifactService, WorkspaceService
from src.agents.middlewares.thread_data import get_thread_data_root
from src.database import User
from src.gateway.access_control import (
    owner_check_session_from_service as _owner_check_session_from_service,
)
from src.gateway.access_control import (
    require_workspace_owner_by_session as _require_workspace_owner,
)
from src.gateway.auth_dependencies import get_current_user, get_current_user_optional
from src.gateway.contracts.artifact import (
    ArtifactResponse,
    ArtifactsListResponse,
    artifact_to_responses,
)
from src.gateway.deps import (
    get_artifact_service,
    get_thread_service,
    get_workspace_service,
)
from src.gateway.resource_access import (
    ensure_workspace_owner_for_service as _ensure_workspace_owner_for_artifact_service,
)
from src.gateway.resource_access import (
    get_workspace_artifact_or_404 as _get_workspace_artifact_or_404,
)
from src.gateway.routers.workspaces_runtime import get_owned_workspace
from src.gateway.validators.artifact import (
    ArtifactCreatePayloadValidator,
    UpdateArtifactValidator,
)
from src.services import ThreadService
from src.services.asset_url_signing import get_asset_url_signer
from src.services.execution_session_service import ExecutionSessionService
from src.services.workspace_skill_labels import (
    normalize_workspace_type,
    resolve_workspace_skill_name,
)
from src.services.workspace_uploads import resolve_workspace_upload_relative_path

router = APIRouter(tags=["artifacts"])

WorkspaceArtifactCreateRequest = ArtifactCreatePayloadValidator
WorkspaceArtifactUpdateRequest = UpdateArtifactValidator
_THREAD_ARTIFACT_VIRTUAL_PREFIX = "/mnt/user-data/"
_UNSAFE_INLINE_MIME_TYPES = {
    "application/xhtml+xml",
    "image/svg+xml",
    "text/html",
}


class AssetSignRequest(BaseModel):
    """Request payload for minting short-lived signed asset URLs."""

    url: str


def _is_within_root(candidate: Path, root: Path) -> bool:
    """Return whether a resolved path remains inside the thread root."""
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        from os.path import commonpath

        return commonpath([str(candidate), str(root)]) == str(root)


def _resolve_thread_file_path(thread_id: str, path: str) -> Path:
    """Resolve a thread virtual file path to the owned filesystem path."""
    normalized_path = f"/{path.lstrip('/')}"
    if not normalized_path.startswith(_THREAD_ARTIFACT_VIRTUAL_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    thread_root = get_thread_data_root(thread_id).resolve()
    relative = normalized_path.removeprefix(_THREAD_ARTIFACT_VIRTUAL_PREFIX)
    candidate = (thread_root / relative).resolve()
    if not _is_within_root(candidate, thread_root):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return candidate


def _build_inline_file_response(actual_path: Path, mime_type: str | None) -> Response:
    """Return an inline response suitable for browser viewing."""
    encoded_filename = quote(actual_path.name)
    normalized_mime = str(mime_type or "").split(";", 1)[0].strip().lower()
    safe_mime_type = (
        "text/plain; charset=utf-8"
        if normalized_mime in _UNSAFE_INLINE_MIME_TYPES
        else (mime_type or "application/octet-stream")
    )
    return FileResponse(
        path=actual_path,
        media_type=safe_mime_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _request_has_valid_signature(request: Request) -> bool:
    return get_asset_url_signer().verify_url(str(request.url))


async def _create_workspace_artifact(
    *,
    workspace_id: str,
    request: ArtifactCreatePayloadValidator,
    current_user: User,
    artifact_service: ArtifactService,
    workspace_service: WorkspaceService,
) -> ArtifactResponse:
    """Create an artifact within a workspace-scoped canonical route."""
    await _ensure_workspace_owner_for_artifact_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )
    if request.created_by_skill is not None:
        workspace = await workspace_service.get(workspace_id)
        workspace_type = normalize_workspace_type(getattr(workspace, "type", None))
        if workspace_type is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Workspace type is not configured",
            )
        if resolve_workspace_skill_name(workspace_type, request.created_by_skill) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid created_by_skill for workspace",
            )

    artifact = await artifact_service.create(
        workspace_id=workspace_id,
        type=request.type,
        title=request.title,
        content=request.content,
        created_by_skill=request.created_by_skill,
        parent_artifact_id=request.parent_artifact_id,
    )

    # SSOT: associate newly-created artifact with its ExecutionSession so that
    # ComputeProjectionService can surface it in the Compute Stage file list.
    if request.execution_session_id:
        session = await ExecutionSessionService(
            artifact_service.db
        ).get_by_id(request.execution_session_id)
        if session is not None:
            await ExecutionSessionService(
                artifact_service.db
            ).update_session_record(
                session,
                commit=False,
                artifact_ids=[
                    *list(session.artifact_ids or []),
                    str(artifact.id),
                ],
            )

    return artifact_to_responses([artifact])[0]


async def _list_workspace_artifacts(
    *,
    workspace_id: str,
    artifact_type: str | None,
    current_user: User,
    artifact_service: ArtifactService,
) -> ArtifactsListResponse:
    """List artifacts within a workspace-scoped canonical route."""
    await _ensure_workspace_owner_for_artifact_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    artifacts = await artifact_service.list_by_workspace(
        workspace_id=workspace_id,
        type=artifact_type,
    )
    return ArtifactsListResponse(
        artifacts=artifact_to_responses(artifacts),
        count=len(artifacts),
    )


async def _get_workspace_artifact(
    *,
    workspace_id: str,
    artifact_id: str,
    current_user: User,
    artifact_service: ArtifactService,
) -> ArtifactResponse:
    """Get a workspace-scoped artifact."""
    artifact = await _get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )
    return artifact_to_responses([artifact])[0]


async def _update_workspace_artifact(
    *,
    workspace_id: str,
    artifact_id: str,
    request: UpdateArtifactValidator,
    current_user: User,
    artifact_service: ArtifactService,
) -> ArtifactResponse:
    """Update a workspace-scoped artifact."""
    await _get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    artifact = await artifact_service.update(
        artifact_id=artifact_id,
        title=request.title,
        content=request.content,
        status=request.status,
        increment_version=True,
    )
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )
    return artifact_to_responses([artifact])[0]


async def _delete_workspace_artifact(
    *,
    workspace_id: str,
    artifact_id: str,
    current_user: User,
    artifact_service: ArtifactService,
) -> dict[str, object]:
    """Delete a workspace-scoped artifact."""
    await _get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    success = await artifact_service.delete(artifact_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )
    return {"success": True, "artifact_id": artifact_id}


async def _get_workspace_artifact_lineage(
    *,
    workspace_id: str,
    artifact_id: str,
    current_user: User,
    artifact_service: ArtifactService,
) -> list[ArtifactResponse]:
    """Get lineage for a workspace-scoped artifact."""
    await _get_workspace_artifact_or_404(
        artifact_service,
        artifact_id=artifact_id,
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        owner_session_resolver=_owner_check_session_from_service,
        require_workspace_owner=_require_workspace_owner,
    )

    lineage = await artifact_service.get_lineage(artifact_id)
    return artifact_to_responses(lineage)


# ============ Endpoints ============


@router.post("/assets/sign", summary="Sign Protected Asset URL")
async def sign_asset_url(
    payload: AssetSignRequest,
    current_user: User = Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, str]:
    """Mint a short-lived signed URL for a protected asset route."""
    raw_url = str(payload.url or "").strip()
    if not raw_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing asset url",
        )
    parsed = urlparse(raw_url)
    if parsed.scheme or parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset url must be a relative API path",
        )
    route_path = parsed.path
    normalized_route_path = (
        route_path.removeprefix("/api")
        if route_path.startswith("/api/")
        else route_path
    )
    if normalized_route_path.startswith("/threads/") and "/artifacts/" in normalized_route_path:
        prefix = "/threads/"
        remainder = normalized_route_path.removeprefix(prefix)
        thread_id, _, _artifact_path = remainder.partition("/artifacts/")
        thread = await thread_service.get_thread(thread_id, str(current_user.id))
        if thread is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thread not found",
            )
    elif normalized_route_path.startswith("/workspaces/") and "/files/" in normalized_route_path:
        prefix = "/workspaces/"
        remainder = normalized_route_path.removeprefix(prefix)
        workspace_id, _, _file_path = remainder.partition("/files/")
        await get_owned_workspace(
            workspace_id=workspace_id,
            current_user=current_user,
            workspace_service=workspace_service,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported asset url",
        )

    signer = get_asset_url_signer()
    signed_url = signer.sign_url(raw_url)
    return {"signed_url": signed_url}


@router.get(
    "/threads/{thread_id}/artifacts/{path:path}",
    summary="Get Thread Artifact File",
)
async def get_thread_artifact(
    thread_id: str,
    path: str,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    thread_service: ThreadService = Depends(get_thread_service),
) -> Response:
    """Serve a thread-scoped sandbox file after ownership verification."""
    if not _request_has_valid_signature(request):
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        thread = await thread_service.get_thread(thread_id, str(current_user.id))
        if thread is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thread not found",
            )

    actual_path = _resolve_thread_file_path(thread_id, path)
    if not actual_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact not found: {path}",
        )
    if not actual_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a file: {path}",
        )

    mime_type, _ = mimetypes.guess_type(actual_path)
    encoded_filename = quote(actual_path.name)
    if request.query_params.get("download"):
        return FileResponse(
            path=actual_path,
            filename=actual_path.name,
            media_type=mime_type,
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{encoded_filename}"
                )
            },
        )
    return _build_inline_file_response(actual_path, mime_type)


@router.get(
    "/workspaces/{workspace_id}/files/{path:path}",
    summary="Get Workspace Upload File",
)
async def get_workspace_file(
    workspace_id: str,
    path: str,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> Response:
    """Serve a canonical workspace upload after ownership verification."""
    if not _request_has_valid_signature(request):
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        await get_owned_workspace(
            workspace_id=workspace_id,
            current_user=current_user,
            workspace_service=workspace_service,
        )

    try:
        actual_path = resolve_workspace_upload_relative_path(workspace_id, path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if not actual_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {path}",
        )
    if not actual_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a file: {path}",
        )

    mime_type, _ = mimetypes.guess_type(actual_path)
    encoded_filename = quote(actual_path.name)
    if request.query_params.get("download"):
        return FileResponse(
            path=actual_path,
            filename=actual_path.name,
            media_type=mime_type,
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{encoded_filename}"
                )
            },
        )
    return _build_inline_file_response(actual_path, mime_type)


@router.post(
    "/workspaces/{workspace_id}/artifacts",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_artifact(
    workspace_id: str,
    request: WorkspaceArtifactCreateRequest,
    current_user: User = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> ArtifactResponse:
    """Canonical workspace-scoped artifact creation route."""
    return await _create_workspace_artifact(
        workspace_id=workspace_id,
        request=request,
        current_user=current_user,
        artifact_service=artifact_service,
        workspace_service=workspace_service,
    )


@router.get(
    "/workspaces/{workspace_id}/artifacts",
    response_model=ArtifactsListResponse,
)
async def list_workspace_artifacts(
    workspace_id: str,
    type: str | None = None,
    current_user: User = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactsListResponse:
    """Canonical workspace-scoped artifact list route."""
    return await _list_workspace_artifacts(
        workspace_id=workspace_id,
        artifact_type=type,
        current_user=current_user,
        artifact_service=artifact_service,
    )


@router.get(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
)
async def get_workspace_artifact(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactResponse:
    """Canonical workspace-scoped artifact detail route."""
    return await _get_workspace_artifact(
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        current_user=current_user,
        artifact_service=artifact_service,
    )


@router.put(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
)
async def update_workspace_artifact(
    workspace_id: str,
    artifact_id: str,
    request: WorkspaceArtifactUpdateRequest,
    current_user: User = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> ArtifactResponse:
    """Canonical workspace-scoped artifact update route."""
    return await _update_workspace_artifact(
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        request=request,
        current_user=current_user,
        artifact_service=artifact_service,
    )


@router.delete("/workspaces/{workspace_id}/artifacts/{artifact_id}")
async def delete_workspace_artifact(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> dict[str, object]:
    """Canonical workspace-scoped artifact delete route."""
    return await _delete_workspace_artifact(
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        current_user=current_user,
        artifact_service=artifact_service,
    )


@router.get(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}/lineage",
    response_model=list[ArtifactResponse],
)
async def get_workspace_artifact_lineage(
    workspace_id: str,
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> list[ArtifactResponse]:
    """Canonical workspace-scoped artifact lineage route."""
    return await _get_workspace_artifact_lineage(
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        current_user=current_user,
        artifact_service=artifact_service,
    )
