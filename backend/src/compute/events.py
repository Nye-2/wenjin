"""Workspace events for compute work-plane sessions."""

from __future__ import annotations

from typing import Any

from src.workspace_events import publish_workspace_event


def serialize_compute_session(session: Any) -> dict[str, Any]:
    """Convert a compute session projection into an event/API payload."""
    return {
        "id": session.id,
        "execution_id": session.execution_id,
        "workspace_id": session.workspace_id,
        "user_id": session.user_id,
        "sandbox_session_id": session.sandbox_session_id,
        "active_view": session.active_view,
        "ui_state": dict(session.ui_state or {}),
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


async def publish_compute_session_event(
    session: Any,
    *,
    event_type: str,
) -> None:
    """Publish a best-effort workspace event for compute session changes."""
    await publish_workspace_event(
        session.workspace_id,
        event_type,
        {"compute_session": serialize_compute_session(session)},
    )
