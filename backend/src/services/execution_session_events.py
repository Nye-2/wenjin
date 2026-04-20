"""Workspace event helpers for execution session lifecycle."""

from __future__ import annotations

from typing import Any

from src.database.models.execution_session import ExecutionSessionRecord
from src.workspace_events import publish_workspace_event


def serialize_execution_session(
    session: ExecutionSessionRecord,
) -> dict[str, Any]:
    """Convert an execution session ORM object into an event-safe payload."""
    return {
        "id": session.id,
        "user_id": session.user_id,
        "workspace_id": session.workspace_id,
        "thread_id": session.thread_id,
        "workspace_type": session.workspace_type,
        "feature_id": session.feature_id,
        "entry_skill_id": session.entry_skill_id,
        "launch_source": session.launch_source,
        "launch_message": session.launch_message,
        "status": session.status,
        "params": session.params or {},
        "task_ids": list(session.task_ids or []),
        "primary_task_id": session.primary_task_id,
        "runtime_snapshot": session.runtime_snapshot,
        "result_summary": session.result_summary,
        "artifact_ids": list(session.artifact_ids or []),
        "next_actions": list(session.next_actions or []),
        "advisory_code": session.advisory_code,
        "last_error": session.last_error,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
    }


async def publish_execution_session_event(
    session: ExecutionSessionRecord,
    *,
    event_type: str,
) -> None:
    """Publish an execution session workspace event."""
    await publish_workspace_event(
        session.workspace_id,
        event_type,
        {
            "execution": serialize_execution_session(session),
        },
    )
