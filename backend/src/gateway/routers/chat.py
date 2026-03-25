"""Chat router for AI conversations."""

import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from src.academic.services import ArtifactService, PaperService, WorkspaceService
from src.agents.lead_agent.feature_bridge import maybe_bridge_workspace_feature
from src.agents.thread_state import ThreadState
from src.config import get_model_config
from src.config.config_loader import get_app_config
from src.database import ChatThread, User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import (
    get_artifact_service,
    get_chat_thread_service,
    get_literature_service,
    get_paper_service,
    get_workspace_service,
)
from src.gateway.routers.chat_contracts import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    GeneratedChatReply,
    ThreadAgentStatusResponse,
    ThreadCreate,
    ThreadListResponse,
    ThreadResponse,
)
from src.gateway.routers.chat_lifecycle import (
    fail_chat_turn as _fail_chat_turn,
)
from src.gateway.routers.chat_lifecycle import (
    persist_chat_reply as _persist_chat_reply,
)
from src.gateway.routers.chat_lifecycle import (
    start_chat_turn as _start_chat_turn,
)
from src.gateway.routers.chat_runtime import (
    build_langchain_messages as _build_langchain_messages,
)
from src.gateway.routers.chat_runtime import (
    coerce_generated_reply as _coerce_generated_reply,
)
from src.gateway.routers.chat_runtime import (
    resolve_workspace_id as _resolve_workspace_id,
)
from src.gateway.routers.chat_serializers import (
    thread_to_response as _thread_to_response,
)
from src.gateway.routers.chat_serializers import (
    thread_to_summary as _thread_to_summary,
)
from src.gateway.routers.chat_streaming import (
    stream_assistant_message_event as _stream_assistant_message_event,
)
from src.gateway.routers.chat_streaming import (
    stream_content_event as _stream_content_event,
)
from src.gateway.routers.chat_streaming import (
    stream_done_event as _stream_done_event,
)
from src.gateway.routers.chat_streaming import (
    stream_error_event as _stream_error_event,
)
from src.gateway.routers.chat_streaming import (
    stream_thread_context_event as _stream_thread_context_event,
)
from src.models import route_chat_model
from src.services import ChatThreadService
from src.services.literature_service import LiteratureService
from src.services.chat_thread_events import (
    publish_thread_deleted,
    publish_thread_updated,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _model_supports_vision(model_name: str) -> bool:
    """Infer whether the selected chat model accepts image inputs."""
    try:
        model_config = get_model_config(model_name)
    except Exception:
        model_config = None

    raw_model = (getattr(model_config, "model", None) or model_name).lower()
    return any(tag in raw_model for tag in ("vision", "vl", "gpt-4o"))


def _subagent_runtime_defaults() -> tuple[bool, int]:
    """Load chat-side subagent defaults from app config."""
    try:
        subagents = get_app_config().subagents
        return bool(subagents.enabled), int(subagents.max_concurrent)
    except Exception:
        return True, 3


def _build_chat_runtime_config(
    *,
    request: ChatRequest,
    thread: ChatThread,
    current_user: User,
    workspace_id: str | None,
    effective_skill: str | None,
    effective_model: str,
) -> RunnableConfig:
    """Build the runtime config used by the chat lead-agent path."""
    subagent_enabled, max_concurrent_subagents = _subagent_runtime_defaults()
    return {
        "configurable": {
            "thread_id": thread.id,
            "workspace_id": workspace_id,
            "user_id": str(current_user.id),
            "model_name": effective_model,
            "supports_vision": _model_supports_vision(effective_model),
            "subagent_enabled": subagent_enabled,
            "max_concurrent_subagents": max_concurrent_subagents,
            "selected_skill": effective_skill,
            "thinking_enabled": request.thinking_enabled,
            "reasoning_effort": request.reasoning_effort,
        }
    }


def _build_chat_initial_state(
    thread: ChatThread,
    *,
    workspace_id: str | None,
    effective_skill: str | None,
) -> dict[str, object]:
    """Build the thread state passed into the chat lead-agent."""
    return {
        "messages": _build_langchain_messages(thread),
        "workspace_id": workspace_id,
        "current_skill": effective_skill,
    }


def _build_fallback_messages(
    *,
    prepared_state: ThreadState,
    config: RunnableConfig,
    apply_prompt_template,
) -> list[object]:
    """Build a fallback simple-model prompt using the same enriched state."""
    fallback_prompt = apply_prompt_template(ThreadState(**prepared_state), config)
    return [
        SystemMessage(content=fallback_prompt),
        *list(prepared_state.get("messages", [])),
    ]


async def _generate_chat_response(
    request: ChatRequest,
    thread: ChatThread,
    current_user: User,
    *,
    workspace_service: WorkspaceService | None = None,
    literature_service: LiteratureService | None = None,
    artifact_service: ArtifactService | None = None,
    paper_service: PaperService | None = None,
) -> GeneratedChatReply:
    """Generate a chat response through the unified lead-agent pipeline."""
    from src.agents.lead_agent.agent import (
        apply_prompt_template,
        build_pipeline,
        make_lead_agent,
        middleware_before_model,
    )

    workspace_id = _resolve_workspace_id(request, thread)
    effective_skill = thread.skill
    effective_model = route_chat_model(
        requested_model=request.model,
        thread_model=thread.model,
        require_tools=True,
    )
    config = _build_chat_runtime_config(
        request=request,
        thread=thread,
        current_user=current_user,
        workspace_id=workspace_id,
        effective_skill=effective_skill,
        effective_model=effective_model,
    )
    initial_state = _build_chat_initial_state(
        thread,
        workspace_id=workspace_id,
        effective_skill=effective_skill,
    )
    middlewares = build_pipeline(
        config,
        workspace_service=workspace_service,
        index_service=literature_service,
        artifact_service=artifact_service,
        paper_service=paper_service,
    )

    try:
        bridged = await maybe_bridge_workspace_feature(
            message=request.message,
            workspace_id=workspace_id,
            thread_id=thread.id,
            user_id=str(current_user.id),
            selected_skill=effective_skill,
        )
        if bridged is not None:
            return GeneratedChatReply(
                content=bridged.content,
                blocks=bridged.blocks,
                metadata=bridged.metadata,
            )

        agent = make_lead_agent(config, middlewares=middlewares)
        result = await agent.ainvoke(initial_state, config=config)
        content = result["messages"][-1].content if result.get("messages") else ""
        return GeneratedChatReply(content=content)

    except Exception:
        logger.exception("Agent failed, falling back to simple model")
        from src.models.factory import create_chat_model

        prepared_state = _build_chat_initial_state(
            thread,
            workspace_id=workspace_id,
            effective_skill=effective_skill,
        )
        try:
            prepared_state = await middleware_before_model(
                ThreadState(**prepared_state),
                config,
                middlewares,
            )
        except Exception:
            logger.debug(
                "Failed to prepare middleware-enriched fallback context",
                exc_info=True,
            )

        model = create_chat_model(
            effective_model,
            thinking_enabled=request.thinking_enabled,
            reasoning_effort=request.reasoning_effort,
        )
        response = await model.ainvoke(
            _build_fallback_messages(
                prepared_state=ThreadState(**prepared_state),
                config=config,
                apply_prompt_template=apply_prompt_template,
            )
        )
        return GeneratedChatReply(content=response.content)


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
    await publish_thread_updated(thread)
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
    chat_thread_service: ChatThreadService = Depends(get_chat_thread_service),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    literature_service: LiteratureService = Depends(get_literature_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    paper_service: PaperService = Depends(get_paper_service),
):
    """Send a message and get a response (non-streaming)."""
    thread = await _start_chat_turn(
        request=request,
        current_user=current_user,
        chat_thread_service=chat_thread_service,
    )

    try:
        reply = _coerce_generated_reply(
            await _generate_chat_response(
                request,
                thread,
                current_user,
                workspace_service=workspace_service,
                literature_service=literature_service,
                artifact_service=artifact_service,
                paper_service=paper_service,
            )
        )
        assistant_message = await _persist_chat_reply(
            thread=thread,
            current_user=current_user,
            user_message=request.message,
            reply=reply,
            chat_thread_service=chat_thread_service,
        )
    except Exception:
        await _fail_chat_turn(thread)
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
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    literature_service: LiteratureService = Depends(get_literature_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
    paper_service: PaperService = Depends(get_paper_service),
):
    """Send a message and get a streaming response."""

    async def generate() -> AsyncGenerator[str, None]:
        thread = await _start_chat_turn(
            request=request,
            current_user=current_user,
            chat_thread_service=chat_thread_service,
        )

        yield _stream_thread_context_event(thread_id=thread.id, skill=thread.skill)

        try:
            reply = _coerce_generated_reply(
                await _generate_chat_response(
                    request,
                    thread,
                    current_user,
                    workspace_service=workspace_service,
                    literature_service=literature_service,
                    artifact_service=artifact_service,
                    paper_service=paper_service,
                )
            )
            if reply.content:
                yield _stream_content_event(reply.content)

            assistant_message = await _persist_chat_reply(
                thread=thread,
                current_user=current_user,
                user_message=request.message,
                reply=reply,
                chat_thread_service=chat_thread_service,
            )
            yield _stream_assistant_message_event(assistant_message)
            yield _stream_done_event()

        except Exception as exc:
            logger.exception("Streaming chat failed")
            await _fail_chat_turn(thread)
            yield _stream_error_event(str(exc))

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
