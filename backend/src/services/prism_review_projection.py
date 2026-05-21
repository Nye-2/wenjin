"""Projection helpers for canonical Prism review items."""

from __future__ import annotations

from typing import Any


def _json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _timestamp(value: Any) -> str | None:
    return value.isoformat() if value else None


def prism_review_item_projection(
    item: Any,
    *,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """Project a canonical ReviewItemProjection into the Prism review card shape."""
    target_ref = _json_object(getattr(item, "target_ref_json", None))
    payload = _json_object(getattr(item, "payload_json", None))
    preview = _json_object(getattr(item, "preview_json", None))
    result = _json_object(getattr(item, "result_json", None))
    path = str(
        target_ref.get("file_path")
        or target_ref.get("path")
        or payload.get("path")
        or preview.get("path")
        or "",
    ).strip()
    logical_key = str(
        target_ref.get("logical_key")
        or payload.get("logical_key")
        or preview.get("logical_key")
        or getattr(item, "source_item_id", None)
        or getattr(item, "id", "")
    )
    status = str(getattr(item, "status", "pending") or "pending")
    actions: list[dict[str, str]] = []
    if status in {"pending", "accepted"}:
        actions = [
            {"action": "preview_prism_change", "label": "预览 diff"},
            {"action": "apply_prism_change", "label": "应用到 Prism"},
            {"action": "reject_prism_change", "label": "忽略并保护"},
        ]
    elif status == "applied":
        actions = [{"action": "revert_prism_change", "label": "撤回写入"}]
    return {
        "id": str(item.id),
        "kind": str(getattr(item, "target_kind", None) or "prism_file_change"),
        "logical_key": logical_key,
        "status": status,
        "title": str(getattr(item, "title", None) or path or logical_key),
        "summary": str(getattr(item, "summary", None) or payload.get("reason") or ""),
        "source": {
            "type": "review_batch",
            "execution_id": payload.get("source_execution_id") or execution_id,
            "task_id": payload.get("source_task_id"),
        },
        "target": {
            "kind": str(getattr(item, "target_kind", None) or "prism_file_change"),
            "file_path": path or None,
            "room": target_ref.get("room"),
            "item_id": target_ref.get("item_id"),
        },
        "preview": {
            "mode": str(preview.get("mode") or "diff"),
            "pending_hash": preview.get("pending_hash") or payload.get("pending_hash"),
            "current_hash": preview.get("current_hash") or payload.get("current_hash"),
            "applied_hash": result.get("applied_hash")
            or preview.get("applied_hash")
            or payload.get("applied_hash"),
            "revert_signature": result.get("revert_signature")
            or preview.get("revert_signature")
            or payload.get("revert_signature"),
        },
        "actions": actions,
        "created_at": _timestamp(getattr(item, "created_at", None)),
        "updated_at": _timestamp(getattr(item, "updated_at", None)),
        "applied_at": _timestamp(getattr(item, "applied_at", None)),
    }
