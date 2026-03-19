"""Chat router for AI conversations."""

import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from src.database import ChatThread, User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_chat_thread_service
from src.models import route_chat_model
from src.services import ChatThreadAccessError, ChatThreadService

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str
    content: str
    timestamp: datetime | None = None


class ChatRequest(BaseModel):
    """Chat request."""

    message: str
    workspace_id: str | None = None
    thread_id: str | None = None
    model: str | None = None
    skill: str | None = None
    thinking_enabled: bool = False
    stream: bool = True


class ChatResponse(BaseModel):
    """Chat response."""

    thread_id: str
    message: ChatMessage
    workspace_id: str | None = None
    skill: str | None = None


class ThreadCreate(BaseModel):
    """Thread creation request."""

    workspace_id: str | None = None
    title: str | None = None
    model: str | None = None
    skill: str | None = None


class ThreadResponse(BaseModel):
    """Thread response."""

    id: str
    workspace_id: str | None
    title: str | None
    model: str
    skill: str | None
    messages: list[ChatMessage]
    created_at: datetime
    updated_at: datetime


class ThreadSummaryResponse(BaseModel):
    """Thread summary used by history and restoration surfaces."""

    id: str
    workspace_id: str | None
    title: str | None
    model: str
    skill: str | None
    message_count: int = 0
    last_message_preview: str | None = None
    last_message_role: str | None = None
    created_at: datetime
    updated_at: datetime


class ThreadListResponse(BaseModel):
    """List wrapper for thread summaries."""

    threads: list[ThreadSummaryResponse]
    count: int


class ThreadAgentStatusResponse(BaseModel):
    """Execution status for a chat thread."""

    thread_id: str
    status: str
    current_skill: str | None = None
    subagent_count: int = 0


def _resolve_workspace_id(request: ChatRequest, thread: ChatThread) -> str | None:
    """Resolve workspace context from request or existing thread."""
    return request.workspace_id or thread.workspace_id


def _build_langchain_messages(thread: ChatThread) -> list:
    """Convert stored thread messages into LangChain message objects."""
    messages = []
    for msg in thread.messages or []:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "system":
            messages.append(SystemMessage(content=msg["content"]))
    return messages


def _thread_messages_to_response(messages: list[dict]) -> list[ChatMessage]:
    """Map persisted JSON messages to API models."""
    return [
        ChatMessage(
            role=message["role"],
            content=message["content"],
            timestamp=message.get("timestamp"),
        )
        for message in messages
    ]


def _truncate_preview(content: str | None, limit: int = 120) -> str | None:
    """Collapse message text into a short single-line preview."""
    normalized = " ".join((content or "").split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


async def _set_thread_agent_status(
    thread_id: str,
    *,
    status: str,
    skill: str | None,
) -> None:
    """Best-effort agent status update for thread-scoped UI polling."""
    try:
        from src.academic.cache.redis_client import redis_client
        from src.config import redis_settings

        if redis_settings.enabled and redis_client._client is not None:
            await redis_client.set_agent_status(thread_id, status, skill=skill, subagent_count=0)
    except Exception:
        logger.debug("Failed to update agent status for thread %s", thread_id, exc_info=True)


async def _generate_chat_response(request: ChatRequest, thread: ChatThread) -> str:
    """Generate a chat response through the unified lead-agent pipeline."""
    workspace_id = _resolve_workspace_id(request, thread)
    effective_skill = thread.skill
    effective_model = route_chat_model(
        requested_model=request.model,
        thread_model=thread.model,
        require_tools=True,
    )

    try:
        from src.agents.lead_agent.agent import make_lead_agent

        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread.id,
                "workspace_id": workspace_id,
                "model_name": effective_model,
                "selected_skill": effective_skill,
                "thinking_enabled": request.thinking_enabled,
            }
        }

        agent = make_lead_agent(config)
        result = await agent.ainvoke(
            {
                "messages": _build_langchain_messages(thread),
                "workspace_id": workspace_id,
                "current_skill": effective_skill,
            },
            config=config,
        )
        return result["messages"][-1].content if result.get("messages") else ""

    except Exception:
        logger.exception("Agent failed, falling back to simple model")
        from src.models.factory import create_chat_model

        model = create_chat_model(effective_model, request.thinking_enabled)
        response = await model.ainvoke(_build_langchain_messages(thread))
        return response.content


def _thread_to_response(thread: ChatThread, include_messages: bool = True) -> ThreadResponse:
    """Convert a thread ORM object to the API response model."""
    return ThreadResponse(
        id=thread.id,
        workspace_id=thread.workspace_id,
        title=thread.title,
        model=thread.model,
        skill=thread.skill,
        messages=_thread_messages_to_response(thread.messages or []) if include_messages else [],
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _thread_to_summary(thread: ChatThread) -> ThreadSummaryResponse:
    """Convert a thread ORM object into a history summary."""
    messages = thread.messages or []
    last_message = messages[-1] if messages else {}
    last_message_content = last_message.get("content") if isinstance(last_message, dict) else None
    last_message_role = last_message.get("role") if isinstance(last_message, dict) else None

    return ThreadSummaryResponse(
        id=thread.id,
        workspace_id=thread.workspace_id,
        title=thread.title,
        model=thread.model,
        skill=thread.skill,
        message_count=len(messages),
        last_message_preview=_truncate_preview(last_message_content),
        last_message_role=last_message_role,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


async def _get_or_create_owned_thread(
    request: ChatRequest,
    current_user: User,
    chat_thread_service: ChatThreadService,
) -> ChatThread:
    """Fetch or create a thread while enforcing owner isolation."""
    try:
        return await chat_thread_service.get_or_create_thread(
            thread_id=request.thread_id,
            user_id=str(current_user.id),
            workspace_id=request.workspace_id,
            model=request.model,
            skill=request.skill,
            skill_explicit="skill" in request.model_fields_set,
        )
    except ChatThreadAccessError as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc


@router.post("/threads", response_model=ThreadResponse)
async def create_thread(
    request: ThreadCreate,
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """Create a new chat thread."""
    thread = await chat_thread_service.create_thread(
        user_id=str(current_user.id),
        workspace_id=request.workspace_id,
        title=request.title,
        model=request.model,
        skill=request.skill,
    )
    return _thread_to_response(thread, include_messages=False)


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

    return _thread_to_response(thread)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """Delete a thread."""
    deleted = await chat_thread_service.delete_thread(thread_id, str(current_user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"success": True}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """Send a message and get a response (non-streaming)."""
    thread = await _get_or_create_owned_thread(request, current_user, chat_thread_service)
    await chat_thread_service.add_message(thread, role="user", content=request.message)
    await _set_thread_agent_status(thread.id, status="running", skill=thread.skill)

    try:
        response_content = await _generate_chat_response(request, thread)

        assistant_message = await chat_thread_service.add_message(
            thread,
            role="assistant",
            content=response_content,
        )
        await chat_thread_service.set_title_if_empty(thread, request.message)
        await _set_thread_agent_status(thread.id, status="completed", skill=thread.skill)
    except Exception:
        await _set_thread_agent_status(thread.id, status="failed", skill=thread.skill)
        raise

    return ChatResponse(
        thread_id=thread.id,
        message=ChatMessage(**assistant_message),
        workspace_id=thread.workspace_id,
        skill=thread.skill,
    )


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """Send a message and get a streaming response."""

    async def generate() -> AsyncGenerator[str, None]:
        thread = await _get_or_create_owned_thread(request, current_user, chat_thread_service)
        await chat_thread_service.add_message(thread, role="user", content=request.message)
        await _set_thread_agent_status(thread.id, status="running", skill=thread.skill)

        yield f"data: {json.dumps({'type': 'thread_id', 'thread_id': thread.id, 'skill': thread.skill})}\n\n"

        try:
            response_content = await _generate_chat_response(request, thread)
            if response_content:
                yield (
                    f"data: {json.dumps({'type': 'content', 'content': response_content})}\n\n"
                )

            await chat_thread_service.add_message(
                thread,
                role="assistant",
                content=response_content,
            )
            await chat_thread_service.set_title_if_empty(thread, request.message)
            await _set_thread_agent_status(thread.id, status="completed", skill=thread.skill)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as exc:
            logger.exception("Streaming chat failed")
            await _set_thread_agent_status(thread.id, status="failed", skill=thread.skill)
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

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
        threads=[_thread_to_summary(thread) for thread in threads],
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

    from src.academic.cache.redis_client import redis_client
    from src.config import redis_settings

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
