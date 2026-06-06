"""Harness event helpers using the existing execution event path."""

from __future__ import annotations

from typing import Any, Literal

from .contracts import HarnessRunContext, HarnessVisibility

HarnessSequenceKind = Literal["tool", "file_change", "budget", "loop", "audit", "final"]


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
    await ctx.publish_event(
        ctx.execution_id,
        f"execution.harness.{event_name}",
        {
            "execution_id": ctx.execution_id,
            "node_id": ctx.node_id,
            "invocation_id": ctx.invocation_id,
            "workspace_id": ctx.workspace_id,
            "visibility": visibility,
            "sequence_kind": sequence_kind,
            "payload": dict(payload),
        },
    )
