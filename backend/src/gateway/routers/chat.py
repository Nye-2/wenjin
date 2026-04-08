"""Chat router for AI conversations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Body, Depends, HTTPException
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
    WorkspaceChatThreadEnsureRequest,
)
from src.gateway.routers.chat_serializers import thread_to_response, thread_to_summary
from src.gateway.routers.chat_streaming import (
    stream_assistant_message_event,
    stream_content_event,
    stream_done_event,
    stream_error_event,
    stream_heartbeat_event,
    stream_reasoning_event,
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
        metadata=request.metadata,
        skill_explicit="skill" in request.model_fields_set,
    )


def _consume_background_task_result(task: asyncio.Task[None]) -> None:
    """Drain detached task exceptions so disconnects do not leak warnings."""
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Detached chat streaming task failed")


async def _await_stream_task(task: asyncio.Task[None]) -> None:
    """Best-effort task cleanup used by the SSE generator."""
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def stream_chat_turn_events(
    request: ChatTurnRequest,
    *,
    actor_id: str,
    handler: ChatTurnHandler,
) -> AsyncGenerator[str, None]:
    """Yield SSE chat events while allowing the turn to finish after disconnects."""
    result_queue: asyncio.Queue[str | None] = asyncio.Queue()
    client_connected = True

    async def _emit(event: str | None) -> None:
        if not client_connected:
            return
        await result_queue.put(event)

    async def _heartbeat() -> None:
        """Send periodic SSE comment lines to keep connection alive."""
        try:
            while True:
                await asyncio.sleep(15)
                await _emit(stream_heartbeat_event())
        except asyncio.CancelledError:
            pass

    async def _process() -> None:
        """Run the actual chat turn and enqueue SSE events."""
        stream_run = None
        try:
            prepared = await handler.prepare_turn(
                request,
                actor_id=actor_id,
            )
            await _emit(
                stream_thread_context_event(
                    thread_id=prepared.thread.id,
                    skill=prepared.thread.skill,
                )
            )
            stream_run = handler.stream_turn(
                prepared,
                actor_id=actor_id,
            )
            async for delta in stream_run:
                if delta.kind == "reasoning":
                    await _emit(stream_reasoning_event(delta.text))
                else:
                    await _emit(stream_content_event(delta.text))
            completed = await stream_run.wait_completed()
            await _emit(
                stream_assistant_message_event(completed.assistant_message)
            )
            await _emit(stream_done_event())
        except ApplicationError as exc:
            if stream_run is not None:
                try:
                    await stream_run.wait_completed()
                except Exception:
                    pass
            await _emit(stream_error_event(exc.message))
        except Exception as exc:
            logger.exception("Streaming chat failed")
            if stream_run is not None:
                try:
                    await stream_run.wait_completed()
                except Exception:
                    pass
            await _emit(stream_error_event(str(exc)))
        finally:
            await _emit(None)

    heartbeat_task = asyncio.create_task(_heartbeat())
    process_task = asyncio.create_task(_process())
    stream_completed = False

    try:
        while True:
            event = await result_queue.get()
            if event is None:
                stream_completed = True
                break
            yield event
    finally:
        client_connected = False
        heartbeat_task.cancel()
        await _await_stream_task(heartbeat_task)

        if process_task.done() or stream_completed:
            await _await_stream_task(process_task)
        else:
            # Keep the turn running so persistence, billing, and status updates still settle.
            process_task.add_done_callback(_consume_background_task_result)


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


@router.post("/workspaces/{workspace_id}/chat-thread", response_model=ThreadResponse)
async def ensure_workspace_chat_thread(
    workspace_id: str,
    request: WorkspaceChatThreadEnsureRequest = Body(
        default_factory=WorkspaceChatThreadEnsureRequest
    ),
    current_user: User = Depends(get_current_user),
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
):
    """Return the canonical chat thread for a workspace, creating it when needed."""
    try:
        thread = await chat_thread_service.get_or_create_thread(
            user_id=str(current_user.id),
            workspace_id=workspace_id,
            model=request.model,
            skill=request.skill,
            skill_explicit="skill" in request.model_fields_set,
        )
    except InvalidRequestedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return thread_to_response(thread)


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

    return StreamingResponse(
        stream_chat_turn_events(
            _to_turn_request(request),
            actor_id=str(current_user.id),
            handler=handler,
        ),
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
