"""Runtime helpers for expert-team user-visible metadata."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.contracts.team_expert import sanitize_expert_preview_item, sanitize_expert_snapshot

from .contracts import AgentInvocation

logger = logging.getLogger(__name__)


def build_expert_node_metadata(
    invocation: AgentInvocation,
    *,
    status: str,
    existing_harness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build bounded expert metadata for an invocation node."""

    harness = dict(existing_harness or {})
    snapshots = sanitize_expert_snapshot_items(invocation.expert_snapshots)
    if not snapshots:
        snapshots = [
            sanitize_expert_snapshot(
                _synthetic_snapshot_payload(invocation, status=status),
            ).model_dump(mode="json", exclude_none=True)
        ]

    preview_items = sanitize_expert_preview_items(invocation.expert_preview_items)

    harness["expert_snapshots"] = _bounded_list(
        [*list(harness.get("expert_snapshots") or []), *snapshots],
        limit=20,
    )
    if preview_items:
        harness["expert_preview_items"] = _bounded_list(
            [*list(harness.get("expert_preview_items") or []), *preview_items],
            limit=20,
        )
    return harness


def build_expert_output_preview_item(
    invocation: AgentInvocation,
    *,
    summary: str,
) -> dict[str, Any] | None:
    """Create a stable user-visible preview item from an invocation output."""

    clean_summary = str(summary or "").strip()
    if not clean_summary:
        return None
    payload = {
        "schema_version": "wenjin.team.expert_preview_item.v1",
        "preview_item_id": f"{invocation.id}.output",
        "execution_id": invocation.execution_id or "",
        "workspace_id": str(invocation.input_brief.get("workspace_id") or ""),
        "owner_agent_invocation_id": invocation.id,
        "owner_role_name": invocation.assigned_role,
        "title": f"{invocation.display_name} 的阶段产出",
        "subtitle": invocation.assigned_role,
        "kind": _output_kind_for_invocation(invocation),
        "summary": clean_summary,
        "status": "ready",
        "created_at": datetime.now(UTC).isoformat(),
    }
    if invocation.expert_snapshots:
        latest = invocation.expert_snapshots[-1]
        if isinstance(latest, dict) and latest.get("snapshot_id"):
            payload["source_snapshot_id"] = str(latest["snapshot_id"])
    return sanitize_expert_preview_item(payload).model_dump(mode="json", exclude_none=True)


def sanitize_expert_snapshot_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            snapshots.append(
                sanitize_expert_snapshot(item).model_dump(mode="json", exclude_none=True),
            )
        except Exception:
            logger.debug("invalid expert snapshot skipped", exc_info=True)
    return snapshots


def sanitize_expert_preview_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preview_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            preview_items.append(
                sanitize_expert_preview_item(item).model_dump(mode="json", exclude_none=True),
            )
        except Exception:
            logger.debug("invalid expert preview item skipped", exc_info=True)
    return preview_items


def _synthetic_snapshot_payload(invocation: AgentInvocation, *, status: str) -> dict[str, Any]:
    expert_profile = dict(invocation.expert_profile or {})
    snapshot_status = _snapshot_status(status)
    status_phrases = expert_profile.get("status_phrases")
    status_phrases = status_phrases if isinstance(status_phrases, dict) else {}
    headline = str(status_phrases.get(snapshot_status) or _default_headline(snapshot_status))
    now = datetime.now(UTC)
    return {
        "schema_version": "wenjin.team.expert_snapshot.v1",
        "snapshot_id": f"{invocation.id}.{snapshot_status}.{int(now.timestamp())}",
        "execution_id": invocation.execution_id or "",
        "workspace_id": str(invocation.input_brief.get("workspace_id") or ""),
        "agent_invocation_id": invocation.id,
        "agent_template_id": invocation.template_id,
        "role_key": invocation.template_id.split(".")[0],
        "role_name": invocation.assigned_role,
        "display_name": invocation.display_name,
        "status": snapshot_status,
        "update_kind": "progress" if snapshot_status in {"queued", "running"} else "output",
        "stage": {"label": _stage_label(snapshot_status)},
        "headline": headline,
        "body": _default_body(invocation, snapshot_status),
        "created_at": now.isoformat(),
    }


def _snapshot_status(status: str) -> str:
    if status == "succeeded":
        return "completed"
    if status in {"queued", "running", "blocked", "completed", "failed"}:
        return status
    if status == "cancelled":
        return "failed"
    return "running"


def _stage_label(status: str) -> str:
    return {
        "queued": "等待接手",
        "running": "正在处理",
        "blocked": "等待补充",
        "completed": "已完成",
        "failed": "未完成",
    }.get(status, "正在处理")


def _default_headline(status: str) -> str:
    return {
        "queued": "正在接手任务",
        "running": "正在处理任务",
        "blocked": "需要补充信息",
        "completed": "已完成阶段产出",
        "failed": "这轮任务未完成",
    }.get(status, "正在处理任务")


def _default_body(invocation: AgentInvocation, status: str) -> str:
    if status == "completed":
        return f"{invocation.display_name} 已完成本轮处理，产出已进入团队流程。"
    if status == "failed":
        message = ""
        if isinstance(invocation.error, dict):
            message = str(invocation.error.get("message") or "")
        return message or f"{invocation.display_name} 本轮未完成，团队会继续处理风险。"
    return f"{invocation.display_name} 正在处理 {invocation.assigned_role} 相关任务。"


def _output_kind_for_invocation(invocation: AgentInvocation) -> str:
    output = invocation.output_report if isinstance(invocation.output_report, dict) else {}
    if isinstance(output.get("papers"), list) or isinstance(output.get("literature"), list):
        return "literature_list"
    if isinstance(output.get("file_changes"), list):
        return "file_change"
    if isinstance(output.get("artifacts"), list) or isinstance(output.get("sandbox_artifacts"), list):
        return "artifact"
    if isinstance(output.get("claims"), list):
        return "claim_set"
    if isinstance(output.get("experiments"), list) or isinstance(output.get("experiment_summary"), dict):
        return "experiment_summary"
    if any(isinstance(output.get(key), str) for key in ("markdown", "report_markdown", "text", "summary")):
        return "report"
    return "document"


def _bounded_list(values: list[Any], *, limit: int) -> list[Any]:
    return values[-limit:]
