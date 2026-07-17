"""Workspace event helpers for persisted threads."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.runtime.serialization import serialize_lc_object
from src.workspace_events import publish_workspace_event

if TYPE_CHECKING:
    from src.dataservice_client.contracts.conversation import ConversationThreadPayload as Thread

logger = logging.getLogger(__name__)


def _truncate_preview(content: str | None, limit: int = 120) -> str | None:
    """Collapse message text into a short single-line preview."""
    normalized = " ".join((content or "").split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _message_preview_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    return str(serialize_lc_object(value))


def _thread_messages_if_loaded(thread: Thread) -> list[dict[str, Any]]:
    """Return persisted messages only when already materialized on the object."""
    candidate: Any = None
    thread_dict = getattr(thread, "__dict__", None)
    if isinstance(thread_dict, dict) and "messages" in thread_dict:
        candidate = thread_dict.get("messages")
    elif not isinstance(thread_dict, dict):
        candidate = getattr(thread, "messages", None)
    return candidate if isinstance(candidate, list) else []


def serialize_thread_summary(thread: Thread) -> dict[str, Any]:
    """Convert a thread ORM object into an event-safe summary payload."""
    messages = _thread_messages_if_loaded(thread)
    last_message = messages[-1] if messages else {}
    last_message_content = (
        last_message.get("content") if isinstance(last_message, dict) else None
    )
    last_message_role = (
        last_message.get("role") if isinstance(last_message, dict) else None
    )
    stored_message_count = getattr(thread, "message_count", None)
    if isinstance(stored_message_count, int) and stored_message_count >= 0:
        message_count = stored_message_count
    else:
        message_count = len(messages)
    stored_last_message_role = getattr(thread, "last_message_role", None)
    resolved_last_message_role = (
        stored_last_message_role
        if isinstance(stored_last_message_role, str) and stored_last_message_role.strip()
        else last_message_role
    )
    stored_last_preview = getattr(thread, "last_message_preview", None)
    resolved_last_preview = (
        stored_last_preview
        if isinstance(stored_last_preview, str) and stored_last_preview.strip()
        else _truncate_preview(_message_preview_text(last_message_content))
    )
    payload = {
        "id": thread.id,
        "workspace_id": thread.workspace_id,
        "title": thread.title,
        "model": thread.model,
        "message_count": message_count,
        "last_message_preview": resolved_last_preview,
        "last_message_role": resolved_last_message_role,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
    }
    return payload


async def publish_thread_updated(thread: Thread) -> None:
    """Publish a thread summary update to the workspace event stream."""
    thread_summary = serialize_thread_summary(thread)
    await publish_workspace_event(
        thread.workspace_id,
        "thread.updated",
        {"thread": thread_summary},
    )


async def publish_thread_deleted(workspace_id: str | None, thread_id: str) -> None:
    """Publish a thread deletion event for workspace consumers."""
    await publish_workspace_event(
        workspace_id,
        "thread.deleted",
        {"thread_id": thread_id},
    )


async def set_thread_status(
    workspace_id: str | None,
    thread_id: str,
    *,
    status: str,
    subagent_count: int = 0,
) -> None:
    """Best-effort thread status update for Redis and workspace SSE."""
    try:
        from src.academic.cache.redis_client import redis_client
        from src.config import redis_settings

        if redis_settings.enabled and redis_client._client is not None:
            await redis_client.set_agent_status(
                thread_id,
                status,
                subagent_count=subagent_count,
            )

        await publish_workspace_event(
            workspace_id,
            "thread.status",
            {
                "thread": {
                    "thread_id": thread_id,
                    "status": status,
                    "subagent_count": subagent_count,
                }
            },
        )
    except Exception:
        logger.debug(
            "Failed to update agent status for thread %s",
            thread_id,
            exc_info=True,
        )
