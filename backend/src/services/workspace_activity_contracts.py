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


def _normalize_result_artifact_ids(result: dict[str, Any] | None) -> list[str]:
    """Read artifact ids from feature task result payloads."""
    if not isinstance(result, dict):
        return []

    raw_ids = result.get("artifact_ids")
    if isinstance(raw_ids, list):
        ids = [str(item).strip() for item in raw_ids if str(item).strip()]
        if ids:
            return ids

    raw_artifacts = result.get("artifacts")
    if isinstance(raw_artifacts, list):
        return [
            artifact_id
            for item in raw_artifacts
            if isinstance(item, dict)
            and (artifact_id := str(item.get("id") or "").strip())
        ]

    return []


def _params_with_result_artifact_seed(
    params: dict[str, Any] | None,
    artifact_ids: list[str],
) -> dict[str, Any] | None:
    """Add an explicit source artifact seed for activity retry routes."""
    if not isinstance(params, dict):
        return None
    normalized = dict(params)
    if not artifact_ids:
        return normalized

    primary_artifact_id = artifact_ids[0]
    normalized.setdefault("source_artifact_id", primary_artifact_id)
    if not isinstance(normalized.get("context_artifact_ids"), list):
        normalized["context_artifact_ids"] = [primary_artifact_id]
    return normalized


def build_task_result_next_actions(
    *,
    payload: dict[str, Any] | None,
    result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build canonical follow-up actions from a completed task result."""
    actions = _normalize_existing_actions(result)

    open_artifact_action = _build_open_artifact_action(result)
    if open_artifact_action is not None:
        _append_unique_action(actions, open_artifact_action)

    prism_action = _build_prism_review_action(result)
    if prism_action is not None:
        _append_unique_action(actions, prism_action)

    rerun_action = _build_rerun_from_artifact_action(payload, result)
    if rerun_action is not None:
        _append_unique_action(actions, rerun_action)

    return actions


def _normalize_existing_actions(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []

    raw_next_actions = result.get("next_actions")
    if not isinstance(raw_next_actions, list):
        return []

    return [dict(item) for item in raw_next_actions if isinstance(item, dict)]


def _append_unique_action(
    actions: list[dict[str, Any]],
    candidate: dict[str, Any],
) -> None:
    signature = _action_signature(candidate)
    for existing in actions:
        if _action_signature(existing) == signature:
            for key, value in candidate.items():
                existing.setdefault(key, value)
            return
    actions.append(candidate)


def _action_signature(action: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(action.get("action") or action.get("kind") or "").strip(),
        str(action.get("feature_id") or "").strip(),
        str(action.get("artifact_id") or "").strip(),
        str(action.get("url") or action.get("href") or "").strip(),
    )


def _build_open_artifact_action(
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None

    artifact_id: str | None = None
    title: str | None = None
    artifact_kind: str | None = None
    artifact_url: str | None = None

    raw_artifacts = result.get("artifacts")
    if isinstance(raw_artifacts, list):
        for item in raw_artifacts:
            if not isinstance(item, dict):
                continue
            artifact_id = _read_string(item.get("id")) or artifact_id
            title = _read_string(item.get("title")) or title
            artifact_kind = (
                _read_string(item.get("artifact_kind"))
                or _read_string(item.get("kind"))
                or _read_string(item.get("type"))
                or artifact_kind
            )
            artifact_url = (
                _read_string(item.get("url"))
                or _read_string(item.get("href"))
                or artifact_url
            )
            if artifact_id or title or artifact_url:
                break

    output_descriptor = _first_room_output_descriptor(result)
    if output_descriptor is not None:
        artifact_kind = output_descriptor.get("artifact_kind") or artifact_kind
        title = output_descriptor.get("title") or title

    action: dict[str, Any] = {
        "action": "open_artifact",
        "label": "查看产物",
    }
    if artifact_id:
        action["artifact_id"] = artifact_id
    if title:
        action["title"] = title
    if artifact_kind:
        action["artifact_kind"] = artifact_kind
    if artifact_url:
        action["url"] = artifact_url

    return action if len(action) > 2 else None


def _build_rerun_from_artifact_action(
    payload: dict[str, Any] | None,
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    feature_id = _read_string(payload.get("feature_id"))
    if not feature_id:
        return None

    artifact_ids = _normalize_result_artifact_ids(result)
    if not artifact_ids:
        return None

    params = payload.get("params")
    seeded_params = _params_with_result_artifact_seed(
        params if isinstance(params, dict) else None,
        artifact_ids,
    )
    if not seeded_params:
        return None

    action: dict[str, Any] = {
        "action": "rerun_from_artifact",
        "label": "基于当前产物继续",
        "feature_id": feature_id,
        **seeded_params,
    }

    skill_id = _read_string(payload.get("skill_id"))
    if skill_id:
        action["skill_id"] = skill_id

    return action


def _build_prism_review_action(
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None

    review_items = _read_review_items(result)
    if not review_items:
        return None

    pending_item = next(
        (
            item
            for item in review_items
            if _read_string(item.get("status")) == "pending"
        ),
        None,
    )
    if pending_item is not None:
        action: dict[str, Any] = {
            "action": "preview_prism_changes",
            "label": "预览待确认修改",
        }
        review_item_id = _read_string(pending_item.get("id"))
        logical_key = _read_string(pending_item.get("logical_key"))
        if review_item_id:
            action["review_item_id"] = review_item_id
        if logical_key:
            action["logical_key"] = logical_key
        return action
    return {
        "action": "open_prism",
        "label": "在 WenjinPrism 中继续编辑",
    }


def _read_review_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw = result.get("review_items")
    if not isinstance(raw, list):
        task_report = result.get("task_report")
        raw = task_report.get("review_items") if isinstance(task_report, dict) else None
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _first_room_output_descriptor(
    result: dict[str, Any] | None,
) -> dict[str, str] | None:
    if not isinstance(result, dict):
        return None

    task_report = result.get("task_report")
    if isinstance(task_report, dict):
        outputs = task_report.get("outputs")
    else:
        outputs = result.get("outputs")

    if not isinstance(outputs, list):
        return None

    for item in outputs:
        if not isinstance(item, dict):
            continue
        kind = _read_string(item.get("kind"))
        if kind not in {"document", "library_item"}:
            continue
        data = item.get("data")
        title = _read_string(item.get("preview"))
        if not title and isinstance(data, dict):
            title = _read_string(data.get("title")) or _read_string(data.get("name"))
        if not title:
            continue
        return {
            "artifact_kind": kind,
            "title": title,
        }

    return None


def _read_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


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


def build_prism_review_activity_item(
    *,
    review_item_id: str,
    workspace_id: str,
    latex_project_id: str,
    logical_key: str,
    title: str | None,
    summary: str | None,
    status: str | None,
    source_execution_id: str | None,
    source_task_id: str | None,
    target_kind: str | None,
    target_file_path: str | None,
    target_room: str | None,
    target_item_id: str | None,
    occurred_at: datetime | str | None,
    created_at: datetime | str | None = None,
    updated_at: datetime | str | None = None,
    applied_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Build the canonical workspace activity item for a Prism review action."""
    normalized_status = str(status or "pending")
    title_prefix = {
        "pending": "待确认稿件修改",
        "applied": "已写入稿件修改",
        "rejected": "已拒绝稿件修改",
        "reverted": "已撤回稿件修改",
    }.get(normalized_status, "稿件修改")
    target_label = title or target_file_path or logical_key or "Prism review item"

    return {
        "id": f"prism_review:{review_item_id}",
        "kind": "prism_review",
        "workspace_id": workspace_id,
        "occurred_at": occurred_at,
        "title": f"{title_prefix}: {target_label}",
        "summary": truncate_activity_preview(summary or target_file_path or logical_key),
        "status": normalized_status,
        "thread_id": None,
        "task_id": source_task_id,
        "artifact_id": None,
        "feature_id": None,
        "skill": None,
        "skill_name": None,
        "created_by_skill": None,
        "created_by_skill_name": None,
        "subagent_type": None,
        "metadata": {
            "latex_project_id": latex_project_id,
            "review_item_id": review_item_id,
            "logical_key": logical_key,
            "source_execution_id": source_execution_id,
            "source_task_id": source_task_id,
            "target_kind": target_kind,
            "target_file_path": target_file_path,
            "target_room": target_room,
            "target_item_id": target_item_id,
            "created_at": _serialize_timestamp(created_at),
            "updated_at": _serialize_timestamp(updated_at),
            "applied_at": _serialize_timestamp(applied_at),
        },
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
        "feature_id": None,
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
    """Build the canonical workspace activity item for a feature task."""
    feature_id = payload.get("feature_id") if isinstance(payload, dict) else None
    title_id = str(feature_id or task_type or "task")
    params = payload.get("params") if isinstance(payload, dict) else None
    result_artifact_ids = _normalize_result_artifact_ids(result)
    retry_params = _params_with_result_artifact_seed(
        params if isinstance(params, dict) else None,
        result_artifact_ids,
    )
    normalized_usage = _normalize_token_usage(token_usage)
    next_actions = build_task_result_next_actions(
        payload=payload if isinstance(payload, dict) else None,
        result=result if isinstance(result, dict) else None,
    )
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
        "artifact_id": result_artifact_ids[0] if result_artifact_ids else None,
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
            "params": retry_params,
            "result_artifact_ids": result_artifact_ids,
            "next_actions": next_actions,
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
    token_usage: dict[str, int] | None = None,
    model_name: str | None = None,
    occurred_at: datetime | str | None,
    created_at: datetime | str | None = None,
    completed_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Build the canonical workspace activity item for a subagent task."""
    normalized_usage = _normalize_token_usage(token_usage)
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
            **({"token_usage": normalized_usage} if normalized_usage is not None else {}),
            **({"model_name": model_name} if model_name else {}),
        },
    }
