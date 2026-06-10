"""Harness event helpers using the existing execution event path."""

from __future__ import annotations

from typing import Any, Literal

from .contracts import HarnessRunContext, HarnessVisibility

HarnessSequenceKind = Literal["tool", "file_change", "budget", "loop", "audit", "final"]
HARNESS_JOURNAL_EVENT_SCHEMA = "wenjin.harness.journal_event.v1"


async def publish_harness_event(
    ctx: HarnessRunContext,
    event_name: str,
    *,
    visibility: HarnessVisibility,
    sequence_kind: HarnessSequenceKind,
    payload: dict[str, Any],
) -> None:
    """Publish a harness event as an existing execution event subtype."""

    if ctx.publish_event is None:
        return
    journal = build_harness_journal_event(
        ctx,
        event_name=event_name,
        sequence_kind=sequence_kind,
        payload=payload,
    )
    envelope = {
        "execution_id": ctx.execution_id,
        "node_id": ctx.node_id,
        "invocation_id": ctx.invocation_id,
        "workspace_id": ctx.workspace_id,
        "visibility": visibility,
        "sequence_kind": sequence_kind,
        "payload": dict(payload),
    }
    if journal is not None:
        envelope["journal"] = journal
    await ctx.publish_event(
        ctx.execution_id,
        f"execution.harness.{event_name}",
        envelope,
    )


def build_harness_journal_event(
    ctx: HarnessRunContext,
    *,
    event_name: str,
    sequence_kind: HarnessSequenceKind,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Build the product-facing summary attached to a harness event."""

    phase = _journal_phase(event_name=event_name, sequence_kind=sequence_kind)
    if phase is None:
        return None
    display_name = _member_display_name(ctx)
    tool_name = str(payload.get("name") or "").strip()
    summary = _journal_summary(phase=phase, display_name=display_name, tool_name=tool_name)
    return {
        "schema": HARNESS_JOURNAL_EVENT_SCHEMA,
        "phase": phase,
        "member": {"id": ctx.node_id, "display_name": display_name},
        "summary": summary,
        "debug_ref": _debug_ref(payload),
    }


def _journal_phase(*, event_name: str, sequence_kind: HarnessSequenceKind) -> str | None:
    if event_name == "tool_call.started":
        return "tool_started"
    if event_name in {"tool_call.completed", "tool_call.failed", "command_audit"}:
        return "tool_completed"
    if event_name == "quality_gate":
        return "quality_gate"
    if sequence_kind == "final":
        return "member_completed"
    return None


def _member_display_name(ctx: HarnessRunContext) -> str:
    candidates = (
        ctx.agent_template.get("display_name"),
        ctx.agent_template.get("label"),
        ctx.agent_template.get("assigned_role"),
        ctx.skill.get("name"),
        ctx.node_id,
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ctx.node_id


def _journal_summary(*, phase: str, display_name: str, tool_name: str) -> str:
    target = tool_name or "工具"
    if phase == "tool_started":
        return f"{display_name}开始 {target}"
    if phase == "tool_completed":
        return f"{display_name}完成 {target}"
    if phase == "quality_gate":
        return f"{display_name}完成质量检查"
    if phase == "member_completed":
        return f"{display_name}完成任务"
    return f"{display_name}更新进度"


def _debug_ref(payload: dict[str, Any]) -> str | None:
    direct = str(payload.get("debug_ref") or "").strip()
    if direct:
        return direct
    refs = payload.get("output_refs")
    if isinstance(refs, list):
        for ref in refs:
            text = str(ref or "").strip()
            if text:
                return text
    return None
