"""Centralized access control helpers for owner isolation.

Provides reusable dependency functions for verifying workspace ownership
and resource access across routers.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.workspace_service import WorkspaceService
from src.database import User, get_db_session
from src.gateway.routers.auth import get_current_user


async def _get_db() -> AsyncSession:  # type: ignore[misc]
    """Dependency to get database session."""
    async with get_db_session() as session:
        yield session


async def _get_workspace_service(
    db: AsyncSession = Depends(_get_db),
) -> WorkspaceService:
    """Get workspace service instance."""
    return WorkspaceService(db)


async def require_workspace_owner(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(_get_workspace_service),
) -> User:
    """Verify that the current user owns the specified workspace.

    Args:
        workspace_id: The workspace ID to check ownership for.
        current_user: The authenticated user (injected).
        workspace_service: Workspace service (injected).

    Returns:
        The authenticated User object (for downstream use).

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
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return current_user
