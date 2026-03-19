"""Shared resource access helpers for gateway routers."""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, status

OwnerSessionResolver = Callable[[Any], Any]
RequireWorkspaceOwner = Callable[[Any, str, str], Awaitable[Any]]


async def ensure_workspace_owner_for_service(
    service: Any,
    workspace_id: str,
    user_id: str,
    *,
    owner_session_resolver: OwnerSessionResolver,
    require_workspace_owner: RequireWorkspaceOwner,
) -> None:
    """Verify workspace ownership using a service-bound session when available."""
    owner_session = owner_session_resolver(service)
    if owner_session is not None:
        await require_workspace_owner(
            owner_session,
            workspace_id=workspace_id,
            user_id=user_id,
        )


async def get_owned_artifact_or_404(
    artifact_service: Any,
    artifact_id: str,
    user_id: str,
    *,
    owner_session_resolver: OwnerSessionResolver,
    require_workspace_owner: RequireWorkspaceOwner,
) -> Any:
    """Load an artifact and enforce owner isolation."""
    artifact = await artifact_service.get(artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )

    await ensure_workspace_owner_for_service(
        artifact_service,
        workspace_id=str(artifact.workspace_id),
        user_id=user_id,
        owner_session_resolver=owner_session_resolver,
        require_workspace_owner=require_workspace_owner,
    )
    return artifact


async def get_workspace_artifact_or_404(
    artifact_service: Any,
    artifact_id: str,
    workspace_id: str,
    user_id: str,
    *,
    owner_session_resolver: OwnerSessionResolver,
    require_workspace_owner: RequireWorkspaceOwner,
) -> Any:
    """Load an artifact and ensure it belongs to the requested workspace."""
    await ensure_workspace_owner_for_service(
        artifact_service,
        workspace_id=workspace_id,
        user_id=user_id,
        owner_session_resolver=owner_session_resolver,
        require_workspace_owner=require_workspace_owner,
    )

    artifact = await artifact_service.get(artifact_id)
    if not artifact or str(artifact.workspace_id) != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )
    return artifact
