"""Canonical Mission-backed workspace activity projection."""

from datetime import datetime
from typing import Any


def _serialize_timestamp(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def serialize_activity_item(item: dict[str, Any]) -> dict[str, Any]:
    """Serialize the compact Mission activity DTO used by API readers."""
    return {
        "id": str(item.get("id") or ""),
        "kind": "mission",
        "workspace_id": (
            str(item["workspace_id"]) if item.get("workspace_id") is not None else None
        ),
        "occurred_at": _serialize_timestamp(item.get("occurred_at")) or "",
        "title": str(item.get("title") or "Research mission"),
        "summary": item.get("summary"),
        "status": item.get("status"),
        "thread_id": (
            str(item["thread_id"]) if item.get("thread_id") is not None else None
        ),
        "mission_id": (
            str(item["mission_id"]) if item.get("mission_id") is not None else None
        ),
        "mission_policy_id": (
            str(item["mission_policy_id"])
            if item.get("mission_policy_id") is not None
            else None
        ),
        "metadata": item.get("metadata") or {},
    }
