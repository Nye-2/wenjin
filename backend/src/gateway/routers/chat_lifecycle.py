"""Shared lifecycle helpers for chat request handling."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.agents.memory.capture import enqueue_memory_capture
from src.database import ChatThread, User
from src.gateway.routers.chat_contracts import ChatRequest, GeneratedChatReply
from src.gateway.routers.chat_runtime import (
    get_or_create_owned_thread as _get_or_create_owned_thread,
)
from src.services import ChatThreadService
from src.services.chat_thread_events import (
    publish_thread_updated,
    set_thread_status,
)


async def start_chat_turn(
    *,
    request: ChatRequest,
    current_user: User,
    chat_thread_service: ChatThreadService,
) -> ChatThread:
    """Create or load a thread, persist the user message, and mark it running."""
    thread = await _get_or_create_owned_thread(request, current_user, chat_thread_service)
    metadata = {}
    if request.attachments:
        metadata["attachments"] = [
            attachment.model_dump()
            for attachment in request.attachments
        ]
    await chat_thread_service.add_message(
        thread,
        role="user",
        content=request.message,
        metadata=metadata or None,
    )
    await set_thread_status(
        thread.workspace_id,
        thread.id,
        status="running",
        skill=thread.skill,
    )
    return thread


async def persist_chat_reply(
    *,
    thread: ChatThread,
    current_user: User,
    user_message: str,
    reply: GeneratedChatReply,
    chat_thread_service: ChatThreadService,
) -> Mapping[str, Any]:
    """Persist assistant output, update derived thread metadata, and mark completed."""
    assistant_message = await chat_thread_service.add_message(
        thread,
        role="assistant",
        content=reply.content,
        blocks=reply.blocks,
        metadata=reply.metadata,
    )
    enqueue_memory_capture(
        thread_id=thread.id,
        user_id=str(current_user.id),
        workspace_id=thread.workspace_id,
        messages=thread.messages or [],
        source="chat.router",
    )
    await chat_thread_service.set_title_if_empty(thread, user_message)
    await publish_thread_updated(thread)
    await set_thread_status(
        thread.workspace_id,
        thread.id,
        status="completed",
        skill=thread.skill,
    )
    return assistant_message


async def fail_chat_turn(thread: ChatThread) -> None:
    """Mark a thread as failed after reply generation or persistence errors."""
    await set_thread_status(
        thread.workspace_id,
        thread.id,
        status="failed",
        skill=thread.skill,
    )
