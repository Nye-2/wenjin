"""Chat router for AI conversations."""

import base64
import logging
import mimetypes
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from src.academic.services import ArtifactService, PaperService, WorkspaceService
from src.agents.lead_agent.feature_bridge import maybe_bridge_workspace_feature
from src.agents.middlewares.thread_data import get_thread_data_root
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
    ChatAttachment,
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
from src.services.chat_billing import (
    extract_message_usage,
    extract_usage_from_agent_result,
    normalize_token_usage,
    usage_to_metadata,
)
from src.services.chat_thread_events import (
    publish_thread_deleted,
    publish_thread_updated,
)
from src.services.literature_service import LiteratureService
from src.tools.builtins.artifacts import (
    build_presented_artifact_items,
    build_presented_artifacts_block,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_THREAD_VIRTUAL_ROOT = "/mnt/user-data/"
_THREAD_UPLOADS_VIRTUAL_ROOT = "/mnt/user-data/uploads/"


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
    attachments: list[ChatAttachment] | None = None,
) -> dict[str, object]:
    """Build the thread state passed into the chat lead-agent."""
    initial_state: dict[str, object] = {
        "messages": _build_langchain_messages(thread),
        "workspace_id": workspace_id,
        "current_skill": effective_skill,
    }
    uploaded_files, viewed_images = _attachment_state_for_chat_turn(
        thread_id=str(thread.id),
        attachments=attachments or [],
    )
    if uploaded_files:
        initial_state["uploaded_files"] = uploaded_files
    if viewed_images:
        initial_state["viewed_images"] = viewed_images
    return initial_state


def _is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        from os.path import commonpath

        return commonpath([str(candidate), str(root)]) == str(root)


def _resolve_thread_virtual_path(thread_id: str, virtual_path: str) -> Path | None:
    normalized_path = f"/{str(virtual_path or '').lstrip('/')}"
    if not normalized_path.startswith(_THREAD_VIRTUAL_ROOT):
        return None

    thread_root = get_thread_data_root(thread_id).resolve()
    relative = normalized_path.removeprefix(_THREAD_VIRTUAL_ROOT)
    candidate = (thread_root / relative).resolve()
    if not _is_within_root(candidate, thread_root):
        return None
    return candidate


def _attachment_state_for_chat_turn(
    *,
    thread_id: str,
    attachments: list[ChatAttachment],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """Build middleware-ready uploaded file and viewed image state from request attachments."""
    uploaded_files: list[dict[str, Any]] = []
    viewed_images: dict[str, dict[str, str]] = {}

    for attachment in attachments:
        path = str(attachment.path or "").strip()
        if not path.startswith(_THREAD_UPLOADS_VIRTUAL_ROOT):
            continue

        uploaded_files.append(
            {
                "name": attachment.name,
                "path": path,
                "size": attachment.size_bytes or 0,
                "kind": attachment.kind,
                "content_type": attachment.content_type,
                "url": attachment.url,
                "paper_id": attachment.paper_id,
                "artifact_id": attachment.artifact_id,
                "metadata": attachment.metadata,
            }
        )

        content_type = (attachment.content_type or "").strip().lower()
        actual_path = _resolve_thread_virtual_path(thread_id, path)
        if not actual_path or not actual_path.is_file():
            continue

        mime_type, _ = mimetypes.guess_type(actual_path.name)
        effective_mime = content_type or mime_type or ""
        if not effective_mime.startswith("image/"):
            continue

        try:
            viewed_images[path] = {
                "base64": base64.b64encode(actual_path.read_bytes()).decode("utf-8"),
                "mime_type": effective_mime,
            }
        except OSError:
            logger.debug("Failed to load uploaded image attachment: %s", actual_path, exc_info=True)

    return uploaded_files, viewed_images


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


def _coerce_message_content(content: Any) -> str:
    """Normalize LangChain message content into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())
        return "\n".join(text_parts)
    return str(content or "")


def _attach_usage_metadata(
    reply: GeneratedChatReply,
    usage: Any,
    *,
    model_name: str | None,
    source: str,
) -> GeneratedChatReply:
    """Attach normalized token usage metadata to a reply when available."""
    normalized_usage = usage if hasattr(usage, "as_dict") else normalize_token_usage(usage)
    if normalized_usage is None:
        return reply

    reply.metadata = dict(reply.metadata or {})
    reply.metadata["usage"] = usage_to_metadata(
        normalized_usage,
        model_name=model_name,
        source=source,
    )
    return reply


async def _ensure_chat_turn_budget(user_id: str) -> None:
    """Reject pure chat turns once free quota is exhausted and credits are empty."""
    from src.database import get_db_session
    from src.services.credit_service import CreditService

    async with get_db_session() as db:
        credit_service = CreditService(db)
        allowed = await credit_service.can_start_chat_turn(user_id)
        if allowed:
            return
        policy = credit_service.get_chat_billing_policy()
        raise HTTPException(
            status_code=402,
            detail=(
                f"Chat 免费额度已用尽。当前策略为前 {policy.free_tokens} tokens 免费，"
                "后续按 token 扣积分，请先补充积分。"
            ),
        )


async def _apply_chat_turn_billing(
    reply: GeneratedChatReply,
    *,
    current_user: User,
    thread: ChatThread,
) -> dict[str, Any] | None:
    """Persist chat token usage and attach billing metadata to the reply."""
    usage_metadata = (
        dict(reply.metadata.get("usage"))
        if isinstance(reply.metadata, dict) and isinstance(reply.metadata.get("usage"), dict)
        else None
    )
    normalized_usage = normalize_token_usage(usage_metadata)
    if normalized_usage is None:
        return None

    from src.database import get_db_session
    from src.services.credit_service import CreditService, InsufficientCreditsError

    try:
        async with get_db_session() as db:
            credit_service = CreditService(db)
            billing = await credit_service.consume_for_chat_usage(
                user_id=str(current_user.id),
                token_usage=normalized_usage,
                model_name=usage_metadata.get("model_name") if usage_metadata else None,
                workspace_id=thread.workspace_id,
                thread_id=thread.id,
                metadata={"source": usage_metadata.get("source", "chat")},
            )
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=402,
            detail=(
                f"积分不足：当前 {exc.current_balance}，"
                f"本轮 Chat 需要 {exc.required}"
            ),
        ) from exc

    reply.metadata = dict(reply.metadata or {})
    reply.metadata["billing"] = billing.as_metadata()
    return billing.as_metadata()


async def _refund_chat_turn_billing(
    *,
    current_user: User,
    billing_metadata: dict[str, Any] | None,
) -> None:
    """Refund chat token billing when reply persistence fails after settlement."""
    transaction_id = (
        str(billing_metadata.get("transaction_id"))
        if isinstance(billing_metadata, dict) and billing_metadata.get("transaction_id")
        else None
    )
    if not transaction_id:
        return

    from src.database import get_db_session
    from src.services.credit_service import CreditService

    async with get_db_session() as db:
        credit_service = CreditService(db)
        await credit_service.refund_consumption(
            user_id=str(current_user.id),
            original_transaction_id=transaction_id,
            reason="聊天回复失败退款",
        )


def _reply_from_agent_result(
    result: dict[str, Any],
    *,
    thread_id: str,
) -> GeneratedChatReply:
    """Convert final agent state into the persisted chat reply contract."""
    messages = list(result.get("messages") or [])
    content = ""
    if messages:
        content = _coerce_message_content(getattr(messages[-1], "content", ""))

    blocks = [
        block
        for block in (result.get("response_blocks") or [])
        if isinstance(block, dict)
    ]
    metadata = (
        dict(result.get("response_metadata"))
        if isinstance(result.get("response_metadata"), dict)
        else {}
    )

    artifacts = [
        artifact
        for artifact in (result.get("artifacts") or [])
        if isinstance(artifact, str) and artifact.strip()
    ]
    if artifacts:
        artifact_items = build_presented_artifact_items(
            artifacts,
            thread_id=thread_id,
        )
        if artifact_items and not isinstance(metadata.get("artifacts"), list):
            metadata["artifacts"] = artifact_items
        if artifact_items and not any(
            isinstance(block, dict) and block.get("type") == "artifacts"
            for block in blocks
        ):
            blocks.append(build_presented_artifacts_block(artifact_items))
        if not content:
            count = len(artifact_items)
            content = f"已生成 {count} 个文件，可直接打开查看。"

    return GeneratedChatReply(
        content=content,
        blocks=blocks,
        metadata=metadata,
    )


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
        attachments=request.attachments,
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

        await _ensure_chat_turn_budget(str(current_user.id))
        agent = make_lead_agent(config, middlewares=middlewares)
        result = await agent.ainvoke(initial_state, config=config)
        reply = _reply_from_agent_result(result, thread_id=thread.id)
        return _attach_usage_metadata(
            reply,
            extract_usage_from_agent_result(result),
            model_name=effective_model,
            source="chat_agent",
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Agent failed, falling back to simple model")
        from src.models.factory import create_chat_model

        prepared_state = _build_chat_initial_state(
            thread,
            workspace_id=workspace_id,
            effective_skill=effective_skill,
            attachments=request.attachments,
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
        reply = GeneratedChatReply(content=response.content)
        return _attach_usage_metadata(
            reply,
            extract_message_usage(response),
            model_name=effective_model,
            source="chat_fallback",
        )


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
        billing_metadata = await _apply_chat_turn_billing(
            reply,
            current_user=current_user,
            thread=thread,
        )
        assistant_message = await _persist_chat_reply(
            thread=thread,
            current_user=current_user,
            user_message=request.message,
            reply=reply,
            chat_thread_service=chat_thread_service,
        )
    except Exception:
        await _refund_chat_turn_billing(
            current_user=current_user,
            billing_metadata=locals().get("billing_metadata"),
        )
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
            billing_metadata = await _apply_chat_turn_billing(
                reply,
                current_user=current_user,
                thread=thread,
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
            await _refund_chat_turn_billing(
                current_user=current_user,
                billing_metadata=locals().get("billing_metadata"),
            )
            await _fail_chat_turn(thread)
            error_message = exc.detail if isinstance(exc, HTTPException) else str(exc)
            yield _stream_error_event(error_message)

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
