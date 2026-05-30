"""Centralized access control helpers for owner isolation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, HTTPException, status

from src.academic.services.workspace_service import WorkspaceService
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps import get_workspace_service


async def require_workspace_owner(
    workspace_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> Any:
    """Verify that the current user owns the specified workspace.

    Args:
        workspace_id: The workspace ID to check ownership for.
        current_user: The authenticated user (injected).
        workspace_service: Workspace service (injected).

    Returns:
        The owned workspace object for downstream use.

    Raises:
        HTTPException 404: If workspace does not exist.
        HTTPException 403: If user does not own the workspace.
    """
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    has_access = await workspace_service.has_active_membership(
        workspace_id=workspace_id,
        user_id=str(current_user.id),
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return workspace


@asynccontextmanager
async def _workspace_dataservice_client(
    dataservice: AsyncDataServiceClient | None,
):
    if dataservice is not None:
        yield dataservice
        return
    async with dataservice_client() as client:
        yield client


async def require_workspace_owner_by_dataservice(
    workspace_id: str,
    user_id: str,
    *,
    dataservice: AsyncDataServiceClient | None = None,
) -> Any:
    """Verify workspace ownership through the canonical Workspace DataService."""
    async with _workspace_dataservice_client(dataservice) as client:
        workspace = await client.get_workspace(workspace_id)
        if workspace is not None:
            has_access = await client.workspace_has_active_membership(
                workspace_id=workspace_id,
                user_id=user_id,
            )
        else:
            has_access = False
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return workspace
