"""Shared memory-capture helpers for chat and agent runtime flows."""

from __future__ import annotations

import re
from copy import copy
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.memory.queue import MemoryQueue, get_default_memory_queue
from src.services.user_memory_service import extract_and_persist_knowledge

UPLOADED_FILES_BLOCK_RE = re.compile(
    r"<uploaded_files>[\s\S]*?</uploaded_files>\n*",
    re.IGNORECASE,
)


def _extract_message_content(content: Any) -> str:
    """Normalize message content into plain text for memory processing."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    if content is None:
        return ""
    return str(content)


def _strip_uploaded_files_markup(content: Any) -> str:
    """Remove injected upload metadata blocks from a message."""
    text = _extract_message_content(content)
    if "<uploaded_files>" not in text.lower():
        return text
    return UPLOADED_FILES_BLOCK_RE.sub("", text).strip()


def filter_messages_for_memory(messages: list[Any]) -> list[Any]:
    """Keep only meaningful user/final assistant turns for memory capture."""
    filtered: list[Any] = []
    skip_next_ai = False

    for message in messages:
        if isinstance(message, HumanMessage):
            cleaned = _strip_uploaded_files_markup(message.content).strip()
            if not cleaned:
                skip_next_ai = True
                continue
            if cleaned != _extract_message_content(message.content).strip():
                clean_message = copy(message)
                clean_message.content = cleaned
                filtered.append(clean_message)
            else:
                filtered.append(message)
            skip_next_ai = False
            continue

        if isinstance(message, AIMessage):
            if getattr(message, "tool_calls", None):
                continue
            if skip_next_ai:
                skip_next_ai = False
                continue
            filtered.append(message)

    return filtered


def messages_to_conversation_text(messages: list[Any], *, limit: int = 12) -> str:
    """Convert recent messages into a compact user/assistant transcript."""
    lines: list[str] = []
    recent_messages = list(messages or [])[-limit:]
    for message in recent_messages:
        role: str | None = None
        content: str | None = None

        if isinstance(message, HumanMessage):
            role = "user"
            content = _strip_uploaded_files_markup(message.content)
        elif isinstance(message, AIMessage):
            role = "assistant"
            if getattr(message, "tool_calls", None):
                continue
            content = _extract_message_content(message.content)
        elif isinstance(message, dict):
            role = str(message.get("role") or "").strip() or None
            raw_content = message.get("content")
            if raw_content is not None:
                content = (
                    _strip_uploaded_files_markup(raw_content)
                    if role == "user"
                    else _extract_message_content(raw_content)
                )

        normalized_content = " ".join((content or "").split())
        if not role or not normalized_content:
            continue
        lines.append(f"{role}: {normalized_content}")
    return "\n".join(lines)


def enqueue_memory_capture(
    *,
    thread_id: str,
    user_id: str | None,
    workspace_id: str | None,
    messages: list[Any],
    source: str | None = None,
    queue: MemoryQueue | None = None,
) -> None:
    """Debounce memory extraction for a chat thread."""
    if not user_id or not thread_id:
        return

    memory_queue = queue or get_default_memory_queue()

    async def _persist(_thread_id: str, queued_messages: list[Any]) -> None:
        conversation_text = messages_to_conversation_text(queued_messages)
        if not conversation_text:
            return
        await extract_and_persist_knowledge(
            str(user_id),
            conversation_text,
            workspace_context=workspace_id,
            source=source or "chat",
        )

    memory_queue.enqueue(thread_id, list(messages), callback=_persist)
