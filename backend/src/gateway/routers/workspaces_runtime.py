"""Runtime helpers for workspace router orchestration."""

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Callable
from inspect import isawaitable
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from src.academic.services.workspace_service import WorkspaceService
from src.gateway.access_control import require_workspace_owner
from src.gateway.auth_dependencies import AccountAuthSubject

if TYPE_CHECKING:
    from src.dataservice_client.contracts.workspace import WorkspacePayload as Workspace


async def get_owned_workspace(
    *,
    workspace_id: str,
    current_user: AccountAuthSubject,
    workspace_service: WorkspaceService,
) -> Workspace:
    """Load a workspace and assert the current user owns it."""

    return await require_workspace_owner(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )


def workspace_type_value(
    workspace: Workspace,
) -> str:
    """Read the enum value for a workspace type."""
    workspace_type = getattr(workspace, "type", None)
    if workspace_type is None:
        raise ValueError("Workspace type is not configured")
    resolved = workspace_type.value if hasattr(workspace_type, "value") else str(workspace_type)
    resolved = resolved.strip()
    if not resolved:
        raise ValueError("Workspace type is not configured")
    return resolved


async def create_workspace_events_response(workspace_id: str) -> StreamingResponse:
    """Create the shared SSE response envelope for workspace-scoped events."""

    from src.workspace_events import stream_workspace_events

    return await create_workspace_events_response_with_stream(
        workspace_id=workspace_id,
        stream_factory=stream_workspace_events,
    )


async def create_workspace_events_response_with_stream(
    *,
    workspace_id: str,
    stream_factory: Callable[[str], AsyncIterable[str] | Awaitable[AsyncIterable[str]]],
) -> StreamingResponse:
    """Create the shared SSE response envelope for workspace-scoped events."""

    stream = stream_factory(workspace_id)
    if isawaitable(stream):
        try:
            stream = await stream
        except Exception as exc:
            from src.workspace_events import WorkspaceEventStreamUnavailable

            if isinstance(exc, WorkspaceEventStreamUnavailable):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Workspace event stream is temporarily unavailable",
                ) from exc
            raise
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
