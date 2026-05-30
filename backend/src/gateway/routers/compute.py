"""Compute Stage API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.academic.services.workspace_service import WorkspaceService
from src.compute.events import serialize_compute_session
from src.compute.models import (
    ComputeProjectionResponse,
    ComputeSessionListResponse,
    ComputeSessionResponse,
)
from src.compute.projection_service import ComputeProjectionService
from src.compute.session_service import ComputeSessionService
from src.database import User
from src.dataservice_client import AsyncDataServiceClient
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_workspace_service
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers.workspaces_runtime import get_owned_workspace

router = APIRouter(tags=["compute"])


@router.get(
    "/workspaces/{workspace_id}/compute/sessions",
    response_model=ComputeSessionListResponse,
)
async def list_workspace_compute_sessions(
    workspace_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ComputeSessionListResponse:
    """List compute sessions for a workspace."""
    await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    sessions = await ComputeSessionService(dataservice=dataservice).list_workspace_sessions(
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        limit=limit,
    )
    return ComputeSessionListResponse(
        items=[
            ComputeSessionResponse(**serialize_compute_session(session))
            for session in sessions
        ],
        count=len(sessions),
    )


@router.get(
    "/compute/sessions/{compute_session_id}",
    response_model=ComputeSessionResponse,
)
async def get_compute_session(
    compute_session_id: str,
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ComputeSessionResponse:
    """Get one compute session shell."""
    session = await ComputeSessionService(dataservice=dataservice).get_by_id(compute_session_id)
    if session is None or str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Compute session not found")
    return ComputeSessionResponse(**serialize_compute_session(session))


@router.get(
    "/compute/sessions/{compute_session_id}/projection",
    response_model=ComputeProjectionResponse,
)
async def get_compute_projection(
    compute_session_id: str,
    current_user: User = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> ComputeProjectionResponse:
    """Get the current Compute Stage projection for one session."""
    projection = await ComputeProjectionService(dataservice=dataservice).get_projection(
        compute_session_id=compute_session_id,
        user_id=str(current_user.id),
    )
    if projection is None:
        raise HTTPException(status_code=404, detail="Compute session not found")
    return ComputeProjectionResponse(**projection)
