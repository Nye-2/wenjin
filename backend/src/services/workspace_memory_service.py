"""Runtime service for hidden workspace-bound memory."""

from __future__ import annotations

import logging
from typing import Any

from src.dataservice_client.contracts.workspace_memory import (
    WorkspaceMemoryItemPayload,
    WorkspaceMemoryMergePayload,
    WorkspaceMemoryRewritePayload,
)
from src.dataservice_client.provider import dataservice_client

logger = logging.getLogger(__name__)
PROMPT_WORKSPACE_MEMORY_CHARS = 3000


def _format_workspace_memory_for_prompt(content_markdown: str | None) -> str:
    content = str(content_markdown or "").strip()
    if not content:
        return ""
    if len(content) > PROMPT_WORKSPACE_MEMORY_CHARS:
        content = content[: PROMPT_WORKSPACE_MEMORY_CHARS - 32].rstrip() + "\n\n- ...\n"
    return f"<workspace_memory>\n{content}\n</workspace_memory>"


async def build_workspace_memory_context(
    workspace_id: str | None,
    *,
    current_context: str | None = None,
) -> str:
    """Load the hidden workspace memory Markdown for prompt injection."""

    del current_context
    if not workspace_id:
        return ""
    try:
        async with dataservice_client() as client:
            document = await client.get_workspace_memory_document(str(workspace_id))
        return _format_workspace_memory_for_prompt(
            document.content_markdown if document is not None else None
        )
    except Exception:
        logger.exception("Failed to load workspace memory")
        return ""


async def merge_workspace_memory_items(
    *,
    workspace_id: str,
    items: list[dict[str, Any]],
    updated_by: str,
    update_reason: str = "execution_commit",
    source_execution_id: str | None = None,
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
                source_execution_id=source_execution_id,
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
    source_execution_id: str | None = None,
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
                source_execution_id=source_execution_id,
                source_thread_id=source_thread_id,
            ),
        )
    return result.changed
