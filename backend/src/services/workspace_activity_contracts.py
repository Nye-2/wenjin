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


def _normalize_token_usage(value: dict[str, Any] | None) -> dict[str, int] | None:
    """Normalize token usage payloads into canonical non-negative counters."""
    if not isinstance(value, dict):
        return None

    def _coerce_int(raw: Any) -> int:
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            return 0
        return max(parsed, 0)

    input_tokens = _coerce_int(value.get("input_tokens", 0) or 0)
    output_tokens = _coerce_int(value.get("output_tokens", 0) or 0)
    total_tokens = _coerce_int(value.get("total_tokens", 0) or 0)
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    if input_tokens <= 0 and output_tokens <= 0 and total_tokens <= 0:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }



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
        "mission_id": (
            str(item["mission_id"]) if item.get("mission_id") is not None else None
        ),
        "mission_policy_id": (
            str(item["mission_policy_id"])
            if item.get("mission_policy_id") is not None
            else None
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



def build_thread_activity_item(
    *,
    thread_id: str,
    workspace_id: str | None,
    title: str | None,
    skill: str | None,
    skill_name: str | None,
    message_count: int,
    last_message_preview: str | None,
    last_message_role: str | None,
    last_message_token_usage: dict[str, int] | None = None,
    thread_token_usage: dict[str, int] | None = None,
    occurred_at: datetime | str | None,
) -> dict[str, Any]:
    """Build the canonical workspace activity item for a thread."""
    metadata: dict[str, Any] = {
        "skill": skill,
        "skill_name": skill_name,
        "message_count": message_count,
        "last_message_role": last_message_role,
    }
    normalized_last_usage = _normalize_token_usage(last_message_token_usage)
    if normalized_last_usage is not None:
        metadata["last_message_token_usage"] = normalized_last_usage
    normalized_thread_usage = _normalize_token_usage(thread_token_usage)
    if normalized_thread_usage is not None:
        metadata["thread_token_usage"] = normalized_thread_usage

    return {
        "id": f"thread:{thread_id}",
        "kind": "thread",
        "workspace_id": workspace_id,
        "occurred_at": occurred_at,
        "title": title or "Thread session",
        "summary": last_message_preview or f"{message_count} messages",
        "status": None,
        "thread_id": thread_id,
        "task_id": None,
        "artifact_id": None,
        "mission_id": None,
        "mission_policy_id": None,
        "skill": skill,
        "skill_name": skill_name,
        "created_by_skill": None,
        "created_by_skill_name": None,
        "subagent_type": None,
        "metadata": metadata,
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
    token_usage: dict[str, int] | None = None,
    subagent_count: int | None = None,
    occurred_at: datetime | str | None,
    created_at: datetime | str | None = None,
    started_at: datetime | str | None = None,
    completed_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Build a workspace activity item for an auxiliary infrastructure task."""
    title_id = str(task_type or "task")
    normalized_usage = _normalize_token_usage(token_usage)
    return {
        "id": f"task:{task_id}",
        "kind": "task",
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
        "mission_id": None,
        "mission_policy_id": None,
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
            "created_at": _serialize_timestamp(created_at),
            "started_at": _serialize_timestamp(started_at),
            "completed_at": _serialize_timestamp(completed_at),
            **({"token_usage": normalized_usage} if normalized_usage is not None else {}),
            **(
                {"subagent_count": max(int(subagent_count or 0), 0)}
                if subagent_count is not None
                else {}
            ),
        },
    }
