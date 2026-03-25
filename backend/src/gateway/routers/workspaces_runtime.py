"""Runtime helpers for workspace router orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi.responses import StreamingResponse

from src.academic.services.workspace_service import WorkspaceService
from src.database import User, Workspace
from src.gateway.access_control import require_workspace_owner


async def get_owned_workspace(
    *,
    workspace_id: str,
    current_user: User,
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
    *,
    default: str | None = None,
) -> str | None:
    """Read the enum value for a workspace type with a fallback."""

    return workspace.type.value if workspace.type else default


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
    stream_factory: Callable[[str], Awaitable[object]],
) -> StreamingResponse:
    """Create the shared SSE response envelope for workspace-scoped events."""

    return StreamingResponse(
        await stream_factory(workspace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
