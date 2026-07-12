"""Runtime service for hidden workspace-bound memory."""

from __future__ import annotations

import html
import logging
from collections.abc import Iterable
from typing import Any

from src.agents.memory.staleness import (
    MemoryStalenessReview,
    review_workspace_memory,
)
from src.dataservice_client.contracts.workspace_memory import (
    WorkspaceMemoryItemPayload,
    WorkspaceMemoryMergePayload,
    WorkspaceMemoryRewritePayload,
)
from src.dataservice_client.provider import dataservice_client

logger = logging.getLogger(__name__)
PROMPT_WORKSPACE_MEMORY_CHARS = 3000
CURRENT_FACTS_CHARS = 1600
ATTENTION_FACTS_CHARS = 900


def _format_workspace_memory_for_prompt(review: MemoryStalenessReview) -> str:
    if not review.facts:
        return ""

    lines = [
        "<workspace_memory>",
        "Only <current_facts> are authoritative. Never silently use items under "
        "<memory_items_to_confirm> as current facts.",
    ]
    if review.current:
        lines.append("<current_facts>")
        lines.extend(
            _bounded_fact_lines(
                (item.fact.content for item in review.current),
                max_chars=CURRENT_FACTS_CHARS,
            )
        )
        lines.append("</current_facts>")
    if review.attention:
        lines.extend(
            [
                "<memory_items_to_confirm>",
                "待确认旧信息：这些内容不得作为当前事实；相关时请先向用户简短确认。",
            ]
        )
        lines.extend(
            _bounded_fact_lines(
                (f"[{item.status.value}] {item.fact.content}" for item in review.attention),
                max_chars=ATTENTION_FACTS_CHARS,
            )
        )
        lines.append("</memory_items_to_confirm>")
    lines.append("</workspace_memory>")
    content = "\n".join(lines)
    if len(content) > PROMPT_WORKSPACE_MEMORY_CHARS:
        raise RuntimeError("workspace memory prompt budget invariant violated")
    return content


def _bounded_fact_lines(values: Iterable[str], *, max_chars: int) -> list[str]:
    lines: list[str] = []
    used = 0
    omitted = False
    for value in values:
        escaped = html.escape(str(value), quote=False)
        available = max_chars - used - 3
        if available <= 1:
            omitted = True
            break
        if len(escaped) > available:
            lines.append(f"- {escaped[: max(1, available - 1)].rstrip()}…")
            omitted = True
            break
        lines.append(f"- {escaped}")
        used += len(escaped) + 3
    if omitted:
        lines.append("- ...")
    return lines


async def build_workspace_memory_context(
    workspace_id: str | None,
    *,
    current_context: str | None = None,
) -> str:
    """Load, review, and format workspace memory for safe prompt injection."""

    if not workspace_id:
        return ""
    try:
        async with dataservice_client() as client:
            document = await client.get_workspace_memory_document(str(workspace_id))
        review = review_workspace_memory(
            document.content_markdown if document is not None else None,
            current_context=current_context,
        )
        return _format_workspace_memory_for_prompt(review)
    except Exception:
        logger.exception("Failed to load workspace memory")
        return ""


async def merge_workspace_memory_items(
    *,
    workspace_id: str,
    items: list[dict[str, Any]],
    updated_by: str,
    update_reason: str = "execution_commit",
    source_mission_id: str | None = None,
    source_thread_id: str | None = None,
) -> int:
    """Merge low-frequency memory items into the hidden workspace memory document."""

    payload_items = [
        WorkspaceMemoryItemPayload(
            category=str(item.get("category") or "context"),
            content=str(item.get("content") or "").strip(),
            confidence=float(item.get("confidence") or 1.0),
        )
        for item in items
        if str(item.get("content") or "").strip()
    ]
    if not payload_items:
        return 0
    async with dataservice_client() as client:
        result = await client.merge_workspace_memory(
            workspace_id,
            WorkspaceMemoryMergePayload(
                workspace_id=workspace_id,
                items=payload_items,
                update_reason=update_reason,
                updated_by=updated_by,
                source_mission_id=source_mission_id,
                source_thread_id=source_thread_id,
            ),
        )
    return 1 if result.changed else 0


async def rewrite_workspace_memory(
    *,
    workspace_id: str,
    content_markdown: str,
    updated_by: str,
    update_reason: str,
    source_mission_id: str | None = None,
    source_thread_id: str | None = None,
) -> bool:
    """Rewrite the hidden workspace memory document after an explicit correction."""

    async with dataservice_client() as client:
        result = await client.rewrite_workspace_memory(
            workspace_id,
            WorkspaceMemoryRewritePayload(
                workspace_id=workspace_id,
                content_markdown=content_markdown,
                update_reason=update_reason,
                updated_by=updated_by,
                source_mission_id=source_mission_id,
                source_thread_id=source_thread_id,
            ),
        )
    return result.changed
