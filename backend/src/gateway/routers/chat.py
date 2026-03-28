"""Chat router for AI conversations."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.application.errors import ApplicationError
from src.application.handlers.chat_turn_handler import (
    ChatTurnHandler,
)
from src.application.results import (
    ChatTurnAttachment,
    ChatTurnRequest,
)
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_chat_thread_service, get_chat_turn_handler
from src.gateway.error_mapping import to_http_exception
from src.gateway.routers.chat_contracts import (
    ChatAttachment,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ThreadAgentStatusResponse,
    ThreadCreate,
    ThreadListResponse,
    ThreadResponse,
)
from src.gateway.routers.chat_serializers import thread_to_response, thread_to_summary
from src.gateway.routers.chat_streaming import (
    stream_assistant_message_event,
    stream_content_event,
    stream_done_event,
    stream_error_event,
    stream_thread_context_event,
)
from src.models.router import InvalidRequestedModelError
from src.academic.cache.redis_client import redis_client
from src.config import redis_settings
from src.services import ChatThreadService
from src.services.chat_thread_events import publish_thread_deleted, publish_thread_updated

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_turn_attachment(attachment: ChatAttachment) -> ChatTurnAttachment:
    return ChatTurnAttachment(**attachment.model_dump())


def _to_turn_request(request: ChatRequest) -> ChatTurnRequest:
    return ChatTurnRequest(
        message=request.message,
        workspace_id=request.workspace_id,
        thread_id=request.thread_id,
        model=request.model,
        skill=request.skill,
        thinking_enabled=request.thinking_enabled,
        reasoning_effort=request.reasoning_effort,
        attachments=tuple(_to_turn_attachment(item) for item in request.attachments),
        skill_explicit="skill" in request.model_fields_set,
    )


@router.post("/threads", response_model=ThreadResponse)
async def create_thread(
    request: ThreadCreate,
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """Create a new chat thread."""
    try:
        thread = await chat_thread_service.create_thread(
            user_id=str(current_user.id),
            workspace_id=request.workspace_id,
            title=request.title,
            model=request.model,
            skill=request.skill,
        )
    except InvalidRequestedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await publish_thread_updated(thread)
    return thread_to_response(thread, include_messages=False)


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread_details(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """Get thread details with messages."""
    thread = await chat_thread_service.get_thread(thread_id, str(current_user.id))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread_to_response(thread)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """Delete a thread."""
    thread = await chat_thread_service.get_thread(thread_id, str(current_user.id))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    deleted = await chat_thread_service.delete_thread(thread_id, str(current_user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")
    await publish_thread_deleted(thread.workspace_id, thread_id)
    return {"success": True}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    handler: ChatTurnHandler = Depends(get_chat_turn_handler),
):
    """Send a message and get a response."""
    try:
        completed = await handler.run_turn(
            _to_turn_request(request),
            actor_id=str(current_user.id),
        )
    except ApplicationError as exc:
        raise to_http_exception(exc) from exc

    return ChatResponse(
        thread_id=completed.thread.id,
        message=ChatMessage(**completed.assistant_message),
        workspace_id=completed.thread.workspace_id,
        skill=completed.thread.skill,
    )


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    handler: ChatTurnHandler = Depends(get_chat_turn_handler),
):
    """Send a message and get a streaming response."""

    async def generate() -> AsyncGenerator[str, None]:
        try:
            prepared = await handler.prepare_turn(
                _to_turn_request(request),
                actor_id=str(current_user.id),
            )
            yield stream_thread_context_event(
                thread_id=prepared.thread.id,
                skill=prepared.thread.skill,
            )

            completed = await handler.complete_turn(
                prepared,
                actor_id=str(current_user.id),
            )
            if completed.reply.content:
                yield stream_content_event(completed.reply.content)
            yield stream_assistant_message_event(completed.assistant_message)
            yield stream_done_event()
        except ApplicationError as exc:
            yield stream_error_event(exc.message)
        except Exception as exc:
            logger.exception("Streaming chat failed")
            yield stream_error_event(str(exc))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/threads", response_model=ThreadListResponse)
async def list_threads(
    workspace_id: str | None = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """List all threads, optionally filtered by workspace."""
    threads = await chat_thread_service.list_threads(
        user_id=str(current_user.id),
        workspace_id=workspace_id,
        limit=limit,
    )
    return ThreadListResponse(
        threads=[thread_to_summary(thread) for thread in threads],
        count=len(threads),
    )


@router.get("/threads/{thread_id}/agent-status", response_model=ThreadAgentStatusResponse)
async def get_thread_agent_status(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """Get the latest agent execution status for a thread."""
    thread = await chat_thread_service.get_thread(thread_id, str(current_user.id))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    payload = {
        "thread_id": thread_id,
        "status": "idle",
        "current_skill": thread.skill,
        "subagent_count": 0,
    }
    if redis_settings.enabled and redis_client._client is not None:
        status = await redis_client.get_agent_status(thread_id)
        if status:
            payload["status"] = status.get("status", "idle")
            payload["current_skill"] = status.get("current_skill") or thread.skill
            try:
                payload["subagent_count"] = int(status.get("subagent_count", 0) or 0)
            except (TypeError, ValueError):
                payload["subagent_count"] = 0

    return ThreadAgentStatusResponse(**payload)
