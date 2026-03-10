"""Chat router for AI conversations."""

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

router = APIRouter()


# ============ Request/Response Models ============

class ChatMessage(BaseModel):
    """A single chat message."""
    role: str  # user, assistant, system
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


# ============ In-Memory Thread Store (TODO: Replace with database) ============

# Simple in-memory store for threads
# In production, this should be persisted to database
_threads_store: dict[str, dict] = {}


def get_thread(thread_id: str) -> dict | None:
    """Get thread by ID."""
    return _threads_store.get(thread_id)


def save_thread(thread_id: str, thread_data: dict) -> None:
    """Save thread data."""
    _threads_store[thread_id] = thread_data


def create_thread_id() -> str:
    """Generate a new thread ID."""
    return str(uuid.uuid4())


# ============ Dependencies ============

async def get_or_create_thread(
    thread_id: str | None = None,
    workspace_id: str | None = None,
    model: str = "gpt-4o",
) -> dict:
    """Get existing thread or create new one."""
    if thread_id and thread_id in _threads_store:
        return _threads_store[thread_id]

    new_thread = {
        "id": create_thread_id(),
        "workspace_id": workspace_id,
        "title": None,
        "model": model,
        "messages": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    _threads_store[new_thread["id"]] = new_thread
    return new_thread


# ============ Endpoints ============

@router.post("/threads", response_model=ThreadResponse)
async def create_thread(request: ThreadCreate):
    """Create a new chat thread."""
    thread = await get_or_create_thread(
        workspace_id=request.workspace_id,
        model=request.model,
    )
    if request.title:
        thread["title"] = request.title

    return ThreadResponse(
        id=thread["id"],
        workspace_id=thread["workspace_id"],
        title=thread["title"],
        model=thread["model"],
        messages=[],
        created_at=thread["created_at"],
        updated_at=thread["updated_at"],
    )


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread_details(thread_id: str):
    """Get thread details with messages."""
    thread = get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = [
        ChatMessage(
            role=msg["role"],
            content=msg["content"],
            timestamp=msg.get("timestamp"),
        )
        for msg in thread.get("messages", [])
    ]

    return ThreadResponse(
        id=thread["id"],
        workspace_id=thread["workspace_id"],
        title=thread["title"],
        model=thread["model"],
        messages=messages,
        created_at=thread["created_at"],
        updated_at=thread["updated_at"],
    )


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a thread."""
    if thread_id not in _threads_store:
        raise HTTPException(status_code=404, detail="Thread not found")

    del _threads_store[thread_id]
    return {"success": True}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message and get a response (non-streaming)."""
    # Get or create thread
    thread = await get_or_create_thread(
        thread_id=request.thread_id,
        workspace_id=request.workspace_id,
        model=request.model,
    )

    # Add user message to thread
    user_msg = {
        "role": "user",
        "content": request.message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    thread["messages"].append(user_msg)

    # Get AI response
    try:
        from src.agents.lead_agent.agent import make_lead_agent

        # Build config
        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread["id"],
                "model_name": request.model,
                "thinking_enabled": request.thinking_enabled,
            }
        }

        # Create agent
        agent = make_lead_agent(config)

        # Build messages for agent
        messages = []
        for msg in thread["messages"]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "system":
                messages.append(SystemMessage(content=msg["content"]))

        # Invoke agent
        result = await agent.ainvoke(
            {"messages": messages},
            config=config,
        )

        # Extract response
        response_content = result["messages"][-1].content if result.get("messages") else ""

    except Exception as e:
        # Fallback to simple model call if agent fails
        logger.exception("Agent failed, falling back to simple model")
        from src.models.factory import create_chat_model
        model = create_chat_model(request.model, request.thinking_enabled)
        response = await model.ainvoke([HumanMessage(content=request.message)])
        response_content = response.content

    # Add assistant message to thread
    assistant_msg = {
        "role": "assistant",
        "content": response_content,
        "timestamp": datetime.utcnow().isoformat(),
    }
    thread["messages"].append(assistant_msg)
    thread["updated_at"] = datetime.utcnow()

    # Auto-generate title if first message
    if not thread["title"] and len(thread["messages"]) <= 2:
        thread["title"] = request.message[:50] + ("..." if len(request.message) > 50 else "")

    return ChatResponse(
        thread_id=thread["id"],
        message=ChatMessage(
            role="assistant",
            content=response_content,
            timestamp=datetime.utcnow(),
        ),
        workspace_id=thread["workspace_id"],
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Send a message and get a streaming response."""

    async def generate() -> AsyncGenerator[str, None]:
        """Generate streaming response."""
        # Get or create thread
        thread = await get_or_create_thread(
            thread_id=request.thread_id,
            workspace_id=request.workspace_id,
            model=request.model,
        )

        # Add user message to thread
        user_msg = {
            "role": "user",
            "content": request.message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        thread["messages"].append(user_msg)

        # Send thread_id first
        yield f"data: {json.dumps({'type': 'thread_id', 'thread_id': thread['id']})}\n\n"

        try:
            from src.models.factory import create_chat_model

            # Create model with streaming
            model = create_chat_model(request.model, request.thinking_enabled)

            # Build messages
            messages = [HumanMessage(content=request.message)]

            # Stream response
            full_response = ""
            async for chunk in model.astream(messages):
                if chunk.content:
                    full_response += chunk.content
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk.content})}\n\n"

            # Add assistant message to thread
            assistant_msg = {
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.utcnow().isoformat(),
            }
            thread["messages"].append(assistant_msg)
            thread["updated_at"] = datetime.utcnow()

            # Send done signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

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
):
    """List all threads, optionally filtered by workspace."""
    threads = list(_threads_store.values())

    if workspace_id:
        threads = [t for t in threads if t["workspace_id"] == workspace_id]

    # Sort by updated_at descending
    threads.sort(key=lambda t: t["updated_at"], reverse=True)

    # Limit results
    threads = threads[:limit]

    return {
        "threads": [
            {
                "id": t["id"],
                "workspace_id": t["workspace_id"],
                "title": t["title"],
                "model": t["model"],
                "message_count": len(t["messages"]),
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
            }
            for t in threads
        ],
        "count": len(threads),
    }
