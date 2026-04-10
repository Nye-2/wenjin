"""Canonical workspace activity payload helpers."""

from datetime import datetime
from typing import Any


def _serialize_timestamp(value: datetime | str | None) -> str | None:
    """Serialize datelike values into event-safe strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def truncate_activity_preview(content: str | None, limit: int = 120) -> str | None:
    """Collapse multi-line text into a short single-line preview."""
    normalized = " ".join((content or "").split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def humanize_activity_identifier(identifier: str) -> str:
    """Convert machine-style identifiers into readable labels."""
    normalized = (identifier or "").strip().replace("-", " ").replace("_", " ")
    return normalized.title() if normalized else "Activity"


def summarize_task_payload(payload: dict[str, Any] | None) -> str | None:
    """Extract a compact task summary from common payload shapes."""
    if not isinstance(payload, dict):
        return None

    params = payload.get("params")
    if isinstance(params, dict):
        for key in ("query", "topic", "paper_title", "title"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return truncate_activity_preview(value)

    for key in ("query", "topic", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return truncate_activity_preview(value)

    return None


def serialize_activity_item(item: dict[str, Any]) -> dict[str, Any]:
    """Convert an activity item into an event/API-safe payload."""
    occurred_at = item.get("occurred_at")
    return {
        "id": str(item.get("id") or ""),
        "kind": str(item.get("kind") or "activity"),
        "workspace_id": (
            str(item["workspace_id"]) if item.get("workspace_id") is not None else None
        ),
        "occurred_at": _serialize_timestamp(occurred_at) or "",
        "title": str(item.get("title") or "Activity"),
        "summary": item.get("summary"),
        "status": item.get("status"),
        "thread_id": str(item["thread_id"]) if item.get("thread_id") is not None else None,
        "task_id": str(item["task_id"]) if item.get("task_id") is not None else None,
        "artifact_id": (
            str(item["artifact_id"]) if item.get("artifact_id") is not None else None
        ),
        "feature_id": (
            str(item["feature_id"]) if item.get("feature_id") is not None else None
        ),
        "skill": str(item["skill"]) if item.get("skill") is not None else None,
        "skill_name": (
            str(item["skill_name"]) if item.get("skill_name") is not None else None
        ),
        "created_by_skill": (
            str(item["created_by_skill"])
            if item.get("created_by_skill") is not None
            else None
        ),
        "created_by_skill_name": (
            str(item["created_by_skill_name"])
            if item.get("created_by_skill_name") is not None
            else None
        ),
        "subagent_type": item.get("subagent_type"),
        "metadata": item.get("metadata") or {},
    }


def build_chat_activity_item(
    *,
    thread_id: str,
    workspace_id: str | None,
    title: str | None,
    skill: str | None,
    skill_name: str | None,
    message_count: int,
    last_message_preview: str | None,
    last_message_role: str | None,
    occurred_at: datetime | str | None,
) -> dict[str, Any]:
    """Build the canonical workspace activity item for a chat thread."""
    return {
        "id": f"chat:{thread_id}",
        "kind": "chat_thread",
        "workspace_id": workspace_id,
        "occurred_at": occurred_at,
        "title": title or "Chat session",
        "summary": last_message_preview or f"{message_count} messages",
        "status": None,
        "thread_id": thread_id,
        "task_id": None,
        "artifact_id": None,
        "feature_id": None,
        "skill": skill,
        "skill_name": skill_name,
        "created_by_skill": None,
        "created_by_skill_name": None,
        "subagent_type": None,
        "metadata": {
            "skill": skill,
            "skill_name": skill_name,
            "message_count": message_count,
            "last_message_role": last_message_role,
        },
    }


def build_task_activity_item(
    *,
    task_id: str,
    workspace_id: str,
    task_type: str | None,
    payload: dict[str, Any] | None,
    status: str | None,
    progress: int | None,
    message: str | None,
    error: str | None,
    result: dict[str, Any] | None = None,
    occurred_at: datetime | str | None,
    created_at: datetime | str | None = None,
    started_at: datetime | str | None = None,
    completed_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Build the canonical workspace activity item for a feature task."""
    feature_id = payload.get("feature_id") if isinstance(payload, dict) else None
    title_id = str(feature_id or task_type or "task")
    params = payload.get("params") if isinstance(payload, dict) else None
    return {
        "id": f"task:{task_id}",
        "kind": "feature_task",
        "workspace_id": workspace_id,
        "occurred_at": occurred_at,
        "title": humanize_activity_identifier(title_id),
        "summary": error or message or summarize_task_payload(payload),
        "status": status,
        "thread_id": (
            str(payload.get("thread_id"))
            if isinstance(payload, dict) and payload.get("thread_id")
            else None
        ),
        "task_id": task_id,
        "artifact_id": None,
        "feature_id": str(feature_id) if feature_id else None,
        "skill": None,
        "skill_name": None,
        "created_by_skill": None,
        "created_by_skill_name": None,
        "subagent_type": None,
        "metadata": {
            "task_type": task_type,
            "progress": progress,
            "message": message,
            "error": error,
            "result": result,
            "action": params.get("action") if isinstance(params, dict) else None,
            "params": params if isinstance(params, dict) else None,
            "created_at": _serialize_timestamp(created_at),
            "started_at": _serialize_timestamp(started_at),
            "completed_at": _serialize_timestamp(completed_at),
        },
    }


def build_subagent_activity_item(
    *,
    workspace_id: str | None,
    task_id: str,
    thread_id: str,
    status: str | None,
    subagent_type: str | None,
    prompt: str | None,
    output_preview: str | None,
    error: str | None,
    occurred_at: datetime | str | None,
    created_at: datetime | str | None = None,
    completed_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Build the canonical workspace activity item for a subagent task."""
    return {
        "id": f"subagent:{task_id}",
        "kind": "subagent_task",
        "workspace_id": workspace_id,
        "occurred_at": occurred_at,
        "title": humanize_activity_identifier(subagent_type or "subagent"),
        "summary": error or output_preview or truncate_activity_preview(prompt),
        "status": status,
        "thread_id": thread_id,
        "task_id": task_id,
        "artifact_id": None,
        "feature_id": None,
        "skill": None,
        "skill_name": None,
        "created_by_skill": None,
        "created_by_skill_name": None,
        "subagent_type": subagent_type,
        "metadata": {
            "prompt": prompt,
            "output_preview": output_preview,
            "error": error,
        },
    }
