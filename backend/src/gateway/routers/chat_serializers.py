"""Serialization helpers for chat router responses."""

from __future__ import annotations

from src.database import ChatThread
from src.services.chat_thread_events import serialize_thread_summary

from .chat_contracts import ChatMessage, ThreadResponse, ThreadSummaryResponse


def thread_messages_to_response(messages: list[dict]) -> list[ChatMessage]:
    """Map persisted JSON messages to API models."""
    return [
        ChatMessage(
            role=message["role"],
            content=message["content"],
            timestamp=message.get("timestamp"),
            blocks=(
                message.get("blocks")
                if isinstance(message.get("blocks"), list)
                else []
            ),
            metadata=(
                message.get("metadata")
                if isinstance(message.get("metadata"), dict)
                else {}
            ),
        )
        for message in messages
    ]


def thread_to_response(
    thread: ChatThread,
    *,
    include_messages: bool = True,
) -> ThreadResponse:
    """Convert a thread ORM object to the API response model."""
    return ThreadResponse(
        id=thread.id,
        workspace_id=thread.workspace_id,
        title=thread.title,
        model=thread.model,
        skill=thread.skill,
        messages=thread_messages_to_response(thread.messages or []) if include_messages else [],
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def thread_to_summary(thread: ChatThread) -> ThreadSummaryResponse:
    """Convert a thread ORM object into a history summary."""
    return ThreadSummaryResponse(**serialize_thread_summary(thread))
