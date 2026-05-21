"""Centralized access control helpers for owner isolation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.workspace_service import WorkspaceService
from src.database import User
from src.dataservice.workspace_api import WorkspaceDataService
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_workspace_service

if TYPE_CHECKING:
    from src.database import Workspace


async def require_workspace_owner(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> Workspace:
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


def owner_check_session_from_service(service: Any) -> AsyncSession | None:
    """Extract a SQLAlchemy session from a service for manual owner checks."""
    db = getattr(service, "db", None)
    return db if isinstance(db, AsyncSession) else None


async def require_workspace_owner_by_session(
    session: AsyncSession,
    workspace_id: str,
    user_id: str,
) -> Workspace:
    """Verify workspace ownership using an existing database session."""
    service = WorkspaceDataService(session)
    workspace = await service.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    has_access = await service.user_has_active_membership(
        workspace_id=workspace_id,
        user_id=user_id,
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return workspace
