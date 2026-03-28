"""Application-layer orchestration for chat turns."""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.academic.services import ArtifactService, PaperService, WorkspaceService
from src.agents.lead_agent.feature_bridge import maybe_bridge_workspace_feature
from src.agents.middlewares.thread_data import get_thread_data_root
from src.agents.memory.capture import enqueue_memory_capture
from src.application.errors import ApplicationError, BadRequestError, NotFoundError, PaymentRequiredError
from src.application.results import (
    ChatTurnAttachment,
    ChatTurnRequest,
    CompletedChatTurn,
    GeneratedChatReply,
    PreparedChatTurn,
)
from src.config import get_model_config
from src.config.llm_config import LLMSettings
from src.config.config_loader import get_app_config
from src.database import ChatThread, get_db_session
from src.models import route_chat_model
from src.models.router import InvalidRequestedModelError
from src.services import ChatThreadAccessError, ChatThreadService
from src.services.chat_billing import (
    extract_usage_from_agent_result,
    normalize_token_usage,
    usage_to_metadata,
)
from src.services.chat_thread_events import publish_thread_updated, set_thread_status
from src.services.credit_service import CreditService
from src.services.literature_service import LiteratureService
from src.tools.builtins.artifacts import (
    build_presented_artifact_items,
    build_presented_artifacts_block,
)

logger = logging.getLogger(__name__)

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


def _resolve_workspace_id(request: ChatTurnRequest, thread: ChatThread) -> str | None:
    return request.workspace_id or thread.workspace_id


def _build_langchain_messages(thread: ChatThread) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for msg in thread.messages or []:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "system":
            messages.append(SystemMessage(content=msg["content"]))
    return messages


def build_chat_runtime_config(
    *,
    request: ChatTurnRequest,
    thread: ChatThread,
    actor_id: str,
    workspace_id: str | None,
    effective_skill: str | None,
    effective_model: str,
) -> RunnableConfig:
    subagent_enabled, max_concurrent_subagents = _subagent_runtime_defaults()
    return {
        "configurable": {
            "thread_id": thread.id,
            "workspace_id": workspace_id,
            "user_id": actor_id,
            "model_name": effective_model,
            "supports_vision": _model_supports_vision(effective_model),
            "subagent_enabled": subagent_enabled,
            "max_concurrent_subagents": max_concurrent_subagents,
            "selected_skill": effective_skill,
            "thinking_enabled": request.thinking_enabled,
            "reasoning_effort": request.reasoning_effort,
        }
    }


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
    attachments: tuple[ChatTurnAttachment, ...],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
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


def build_chat_initial_state(
    thread: ChatThread,
    *,
    workspace_id: str | None,
    effective_skill: str | None,
    attachments: tuple[ChatTurnAttachment, ...],
) -> dict[str, object]:
    initial_state: dict[str, object] = {
        "messages": _build_langchain_messages(thread),
        "workspace_id": workspace_id,
        "current_skill": effective_skill,
    }
    uploaded_files, viewed_images = _attachment_state_for_chat_turn(
        thread_id=str(thread.id),
        attachments=attachments,
    )
    if uploaded_files:
        initial_state["uploaded_files"] = uploaded_files
    if viewed_images:
        initial_state["viewed_images"] = viewed_images
    return initial_state


def _coerce_message_content(content: Any) -> str:
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


def _reply_from_agent_result(
    result: dict[str, Any],
    *,
    thread_id: str,
) -> GeneratedChatReply:
    messages = list(result.get("messages") or [])
    content = ""
    if messages:
        content = _coerce_message_content(getattr(messages[-1], "content", ""))

    blocks = [
        block
        for block in (result.get("response_blocks") or [])
        if isinstance(block, dict)
    ]
    raw_response_metadata = result.get("response_metadata")
    metadata = (
        dict(raw_response_metadata)
        if isinstance(raw_response_metadata, dict)
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


class ChatTurnHandler:
    """Application-layer orchestration for one chat turn."""

    def __init__(
        self,
        *,
        chat_thread_service: ChatThreadService,
        workspace_service: WorkspaceService | None = None,
        literature_service: LiteratureService | None = None,
        artifact_service: ArtifactService | None = None,
        paper_service: PaperService | None = None,
    ) -> None:
        self.chat_thread_service = chat_thread_service
        self.workspace_service = workspace_service
        self.literature_service = literature_service
        self.artifact_service = artifact_service
        self.paper_service = paper_service

    async def prepare_turn(
        self,
        request: ChatTurnRequest,
        *,
        actor_id: str,
    ) -> PreparedChatTurn:
        thread = await self._get_or_create_owned_thread(request, actor_id=actor_id)

        metadata = {}
        if request.attachments:
            metadata["attachments"] = [
                asdict(attachment)
                for attachment in request.attachments
            ]

        await self.chat_thread_service.add_message(
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
        return PreparedChatTurn(request=request, thread=thread)

    async def complete_turn(
        self,
        prepared: PreparedChatTurn,
        *,
        actor_id: str,
    ) -> CompletedChatTurn:
        request = prepared.request
        thread = prepared.thread

        try:
            reply = await self._generate_chat_response(
                request,
                thread,
                actor_id=actor_id,
            )
            billing_metadata = await self._apply_chat_turn_billing(
                reply,
                actor_id=actor_id,
                thread=thread,
            )
            assistant_message = await self._persist_chat_reply(
                thread=thread,
                actor_id=actor_id,
                user_message=request.message,
                reply=reply,
            )
        except Exception:
            await self._refund_chat_turn_billing(
                actor_id=actor_id,
                billing_metadata=locals().get("billing_metadata"),
            )
            await self._fail_chat_turn(thread)
            raise

        return CompletedChatTurn(
            thread=thread,
            assistant_message=dict(assistant_message),
            reply=reply,
        )

    async def run_turn(
        self,
        request: ChatTurnRequest,
        *,
        actor_id: str,
    ) -> CompletedChatTurn:
        prepared = await self.prepare_turn(request, actor_id=actor_id)
        return await self.complete_turn(prepared, actor_id=actor_id)

    async def _get_or_create_owned_thread(
        self,
        request: ChatTurnRequest,
        *,
        actor_id: str,
    ) -> ChatThread:
        try:
            return await self.chat_thread_service.get_or_create_thread(
                thread_id=request.thread_id,
                user_id=actor_id,
                workspace_id=request.workspace_id,
                model=request.model,
                skill=request.skill,
                skill_explicit=request.skill_explicit,
            )
        except ChatThreadAccessError as exc:
            raise NotFoundError("Thread not found") from exc
        except InvalidRequestedModelError as exc:
            raise BadRequestError(str(exc)) from exc

    async def _apply_chat_turn_billing(
        self,
        reply: GeneratedChatReply,
        *,
        actor_id: str,
        thread: ChatThread,
    ) -> dict[str, Any] | None:
        raw_usage = (
            reply.metadata.get("usage")
            if isinstance(reply.metadata, dict)
            else None
        )
        usage_metadata = (
            dict(raw_usage)
            if isinstance(raw_usage, dict)
            else None
        )
        normalized_usage = normalize_token_usage(usage_metadata)
        if normalized_usage is None:
            return None

        async with get_db_session() as db:
            credit_service = CreditService(db)
            billing = await credit_service.consume_for_chat_usage(
                user_id=actor_id,
                token_usage=normalized_usage,
                model_name=usage_metadata.get("model_name") if usage_metadata else None,
                workspace_id=thread.workspace_id,
                thread_id=thread.id,
                metadata={
                    "source": (
                        usage_metadata.get("source", "chat")
                        if usage_metadata is not None
                        else "chat"
                    )
                },
            )

        reply.metadata = dict(reply.metadata or {})
        reply.metadata["billing"] = billing.as_metadata()
        return billing.as_metadata()

    async def _refund_chat_turn_billing(
        self,
        *,
        actor_id: str,
        billing_metadata: dict[str, Any] | None,
    ) -> None:
        transaction_id = (
            str(billing_metadata.get("transaction_id"))
            if isinstance(billing_metadata, dict) and billing_metadata.get("transaction_id")
            else None
        )
        if not transaction_id:
            return

        async with get_db_session() as db:
            credit_service = CreditService(db)
            await credit_service.refund_consumption(
                user_id=actor_id,
                original_transaction_id=transaction_id,
                reason="聊天回复失败退款",
            )

    async def _persist_chat_reply(
        self,
        *,
        thread: ChatThread,
        actor_id: str,
        user_message: str,
        reply: GeneratedChatReply,
    ) -> Mapping[str, Any]:
        assistant_message = await self.chat_thread_service.add_message(
            thread,
            role="assistant",
            content=reply.content,
            blocks=reply.blocks,
            metadata=reply.metadata,
        )
        enqueue_memory_capture(
            thread_id=thread.id,
            user_id=actor_id,
            workspace_id=thread.workspace_id,
            messages=thread.messages or [],
            source="chat.handler",
        )
        await self.chat_thread_service.set_title_if_empty(thread, user_message)
        await publish_thread_updated(thread)
        await set_thread_status(
            thread.workspace_id,
            thread.id,
            status="completed",
            skill=thread.skill,
        )
        return assistant_message

    async def _fail_chat_turn(self, thread: ChatThread) -> None:
        await set_thread_status(
            thread.workspace_id,
            thread.id,
            status="failed",
            skill=thread.skill,
        )

    async def _generate_chat_response(
        self,
        request: ChatTurnRequest,
        thread: ChatThread,
        *,
        actor_id: str,
    ) -> GeneratedChatReply:
        return await generate_chat_response(
            request,
            thread,
            actor_id=actor_id,
            workspace_service=self.workspace_service,
            literature_service=self.literature_service,
            artifact_service=self.artifact_service,
            paper_service=self.paper_service,
        )


async def ensure_chat_turn_budget(actor_id: str) -> None:
    """Reject pure chat turns once free quota is exhausted and credits are empty."""
    async with get_db_session() as db:
        credit_service = CreditService(db)
        allowed = await credit_service.can_start_chat_turn(actor_id)
        if allowed:
            return
        policy = credit_service.get_chat_billing_policy()
        raise PaymentRequiredError(
            f"Chat 免费额度已用尽。当前策略为前 {policy.free_tokens} tokens 免费，"
            "后续按 token 扣积分，请先补充积分。"
        )


async def generate_chat_response(
    request: ChatTurnRequest,
    thread: ChatThread,
    *,
    actor_id: str,
    workspace_service: WorkspaceService | None = None,
    literature_service: LiteratureService | None = None,
    artifact_service: ArtifactService | None = None,
    paper_service: PaperService | None = None,
) -> GeneratedChatReply:
    """Generate a chat response through the unified lead-agent pipeline."""
    from src.agents.lead_agent.agent import build_pipeline, make_lead_agent

    workspace_id = _resolve_workspace_id(request, thread)
    effective_skill = thread.skill
    effective_model = route_chat_model(
        requested_model=request.model,
        thread_model=thread.model,
        require_tools=True,
    )
    config = build_chat_runtime_config(
        request=request,
        thread=thread,
        actor_id=actor_id,
        workspace_id=workspace_id,
        effective_skill=effective_skill,
        effective_model=effective_model,
    )
    initial_state = build_chat_initial_state(
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
        memory_capture_enabled=False,
    )

    bridged = await maybe_bridge_workspace_feature(
        message=request.message,
        workspace_id=workspace_id,
        thread_id=thread.id,
        user_id=actor_id,
        selected_skill=effective_skill,
    )
    if bridged is not None:
        return GeneratedChatReply(
            content=bridged.content,
            blocks=bridged.blocks,
            metadata=bridged.metadata,
        )

    await ensure_chat_turn_budget(actor_id)
    agent = cast(Any, make_lead_agent(config, middlewares=middlewares))
    try:
        result = await asyncio.wait_for(
            agent.ainvoke(initial_state, config=config),
            timeout=LLMSettings.AGENT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "Agent timed out after %.0fs for thread %s",
            LLMSettings.AGENT_TIMEOUT,
            thread.id,
        )
        raise ApplicationError("AI 响应超时，请稍后重试或简化您的问题。")
    reply = _reply_from_agent_result(result, thread_id=thread.id)
    return _attach_usage_metadata(
        reply,
        extract_usage_from_agent_result(result),
        model_name=effective_model,
        source="chat_agent",
    )
