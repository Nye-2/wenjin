"""Serialization helpers for thread management responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.runtime.serialization import serialize_lc_object
from src.services.thread_events import serialize_thread_summary

from .thread_contracts import ThreadMessage, ThreadResponse, ThreadSummaryResponse

if TYPE_CHECKING:
    from src.database import Thread


def thread_messages_to_response(messages: list[dict[str, Any]]) -> list[ThreadMessage]:
    """Map persisted JSON messages to API models."""
    rendered_messages: list[ThreadMessage] = []
    for message in messages:
        raw_content = message.get("content")
        safe_content = (
            raw_content
            if isinstance(raw_content, str)
            else str(serialize_lc_object(raw_content) or "")
        )
        raw_blocks = serialize_lc_object(message.get("blocks"))
        raw_metadata = serialize_lc_object(message.get("metadata"))
        rendered_messages.append(
            ThreadMessage(
                role=str(message.get("role") or ""),
                content=safe_content,
                timestamp=message.get("timestamp"),
                blocks=raw_blocks if isinstance(raw_blocks, list) else [],
                metadata=raw_metadata if isinstance(raw_metadata, dict) else {},
            )
        )

    return rendered_messages


def thread_to_response(
    thread: Thread,
    *,
    include_messages: bool = True,
    messages: list[dict[str, Any]] | None = None,
) -> ThreadResponse:
    """Convert a thread ORM object to the API response model."""
    resolved_messages = messages if include_messages and messages is not None else []
    return ThreadResponse(
        id=thread.id,
        workspace_id=thread.workspace_id,
        title=thread.title,
        model=thread.model,
        skill=thread.skill,
        skill_name=None,
        messages=thread_messages_to_response(resolved_messages),
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def thread_to_summary(thread: Thread) -> ThreadSummaryResponse:
    """Convert a thread ORM object into a history summary."""
    return ThreadSummaryResponse(**serialize_thread_summary(thread))
