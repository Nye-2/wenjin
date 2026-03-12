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
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import ChatThread, User
from src.gateway.routers.auth import get_current_user
from src.gateway.routers.workspaces import get_db
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
    model: str = "gpt-4o"
    thinking_enabled: bool = False
    stream: bool = True


class ChatResponse(BaseModel):
    """Chat response."""

    thread_id: str
    message: ChatMessage
    workspace_id: str | None = None


class ThreadCreate(BaseModel):
    """Thread creation request."""

    workspace_id: str | None = None
    title: str | None = None
    model: str = "gpt-4o"


class ThreadResponse(BaseModel):
    """Thread response."""

    id: str
    workspace_id: str | None
    title: str | None
    model: str
    messages: list[ChatMessage]
    created_at: datetime
    updated_at: datetime


async def get_chat_thread_service(
    db: AsyncSession = Depends(get_db),
) -> ChatThreadService:
    """Get chat thread service instance."""
    return ChatThreadService(db)


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


async def _generate_chat_response(request: ChatRequest, thread: ChatThread) -> str:
    """Generate a chat response through the unified lead-agent pipeline."""
    workspace_id = _resolve_workspace_id(request, thread)

    try:
        from src.agents.lead_agent.agent import make_lead_agent

        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread.id,
                "workspace_id": workspace_id,
                "model_name": request.model,
                "thinking_enabled": request.thinking_enabled,
            }
        }

        agent = make_lead_agent(config)
        result = await agent.ainvoke(
            {
                "messages": _build_langchain_messages(thread),
                "workspace_id": workspace_id,
            },
            config=config,
        )
        return result["messages"][-1].content if result.get("messages") else ""

    except Exception:
        logger.exception("Agent failed, falling back to simple model")
        from src.models.factory import create_chat_model

        model = create_chat_model(request.model, request.thinking_enabled)
        response = await model.ainvoke(_build_langchain_messages(thread))
        return response.content


def _thread_to_response(thread: ChatThread, include_messages: bool = True) -> ThreadResponse:
    """Convert a thread ORM object to the API response model."""
    return ThreadResponse(
        id=thread.id,
        workspace_id=thread.workspace_id,
        title=thread.title,
        model=thread.model,
        messages=_thread_messages_to_response(thread.messages or []) if include_messages else [],
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

    response_content = await _generate_chat_response(request, thread)

    assistant_message = await chat_thread_service.add_message(
        thread,
        role="assistant",
        content=response_content,
    )
    await chat_thread_service.set_title_if_empty(thread, request.message)

    return ChatResponse(
        thread_id=thread.id,
        message=ChatMessage(**assistant_message),
        workspace_id=thread.workspace_id,
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

        yield f"data: {json.dumps({'type': 'thread_id', 'thread_id': thread.id})}\n\n"

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
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as exc:
            logger.exception("Streaming chat failed")
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


@router.get("/threads")
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
    return {
        "threads": [
            {
                "id": thread.id,
                "workspace_id": thread.workspace_id,
                "title": thread.title,
                "model": thread.model,
                "message_count": len(thread.messages or []),
                "created_at": thread.created_at,
                "updated_at": thread.updated_at,
            }
            for thread in threads
        ],
        "count": len(threads),
    }
