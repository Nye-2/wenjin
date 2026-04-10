"""Workspace event helpers for persisted chat threads."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.database import get_db_session
from src.services.workspace_skill_labels import (
    get_workspace_type,
    resolve_thread_skill_name,
    resolve_workspace_skill_name,
)
from src.services.workspace_activity_contracts import (
    build_chat_activity_item,
    serialize_activity_item,
)
from src.workspace_events import publish_workspace_event

if TYPE_CHECKING:
    from src.database import ChatThread

logger = logging.getLogger(__name__)


def _truncate_preview(content: str | None, limit: int = 120) -> str | None:
    """Collapse message text into a short single-line preview."""
    normalized = " ".join((content or "").split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def serialize_thread_summary(thread: ChatThread) -> dict[str, Any]:
    """Convert a thread ORM object into an event-safe summary payload."""
    messages = thread.messages or []
    last_message = messages[-1] if messages else {}
    last_message_content = (
        last_message.get("content") if isinstance(last_message, dict) else None
    )
    last_message_role = (
        last_message.get("role") if isinstance(last_message, dict) else None
    )

    return {
        "id": thread.id,
        "workspace_id": thread.workspace_id,
        "title": thread.title,
        "model": thread.model,
        "skill": thread.skill,
        "skill_name": resolve_thread_skill_name(thread),
        "message_count": len(messages),
        "last_message_preview": _truncate_preview(last_message_content),
        "last_message_role": last_message_role,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
    }


async def publish_thread_updated(thread: ChatThread) -> None:
    """Publish a thread summary update to the workspace event stream."""
    thread_summary = serialize_thread_summary(thread)
    await publish_workspace_event(
        thread.workspace_id,
        "thread.updated",
        {
            "thread": thread_summary,
            "activity": serialize_activity_item(
                build_chat_activity_item(
                    thread_id=str(thread_summary["id"]),
                    workspace_id=(
                        str(thread_summary["workspace_id"])
                        if thread_summary.get("workspace_id") is not None
                        else None
                    ),
                    title=(
                        str(thread_summary["title"])
                        if thread_summary.get("title") is not None
                        else None
                    ),
                    skill=(
                        str(thread_summary["skill"])
                        if thread_summary.get("skill") is not None
                        else None
                    ),
                    skill_name=(
                        str(thread_summary["skill_name"])
                        if thread_summary.get("skill_name") is not None
                        else None
                    ),
                    message_count=int(thread_summary.get("message_count") or 0),
                    last_message_preview=(
                        str(thread_summary["last_message_preview"])
                        if thread_summary.get("last_message_preview") is not None
                        else None
                    ),
                    last_message_role=(
                        str(thread_summary["last_message_role"])
                        if thread_summary.get("last_message_role") is not None
                        else None
                    ),
                    occurred_at=(
                        str(thread_summary["updated_at"])
                        if thread_summary.get("updated_at") is not None
                        else None
                    ),
                )
            ),
        },
    )


async def publish_thread_deleted(workspace_id: str | None, thread_id: str) -> None:
    """Publish a thread deletion event for workspace consumers."""
    await publish_workspace_event(
        workspace_id,
        "thread.deleted",
        {"thread_id": thread_id, "activity_id": f"chat:{thread_id}"},
    )


async def set_thread_status(
    workspace_id: str | None,
    thread_id: str,
    *,
    status: str,
    skill: str | None,
    skill_name: str | None = None,
    subagent_count: int = 0,
) -> None:
    """Best-effort thread status update for Redis and workspace SSE."""
    resolved_skill_name = skill_name
    if resolved_skill_name is None and skill:
        try:
            async with get_db_session() as db:
                workspace_type = await get_workspace_type(db, workspace_id)
            resolved_skill_name = resolve_workspace_skill_name(workspace_type, skill)
        except Exception:
            logger.debug(
                "Failed to resolve workspace skill label for thread %s",
                thread_id,
                exc_info=True,
            )

    try:
        from src.academic.cache.redis_client import redis_client
        from src.config import redis_settings

        if redis_settings.enabled and redis_client._client is not None:
            await redis_client.set_agent_status(
                thread_id,
                status,
                skill=skill,
                skill_name=resolved_skill_name,
                subagent_count=subagent_count,
                clear_skill=skill is None,
            )

        await publish_workspace_event(
            workspace_id,
            "thread.status",
            {
                "thread": {
                    "thread_id": thread_id,
                    "status": status,
                    "current_skill": skill,
                    "current_skill_name": resolved_skill_name,
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
