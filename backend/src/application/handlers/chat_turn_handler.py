"""Application-layer orchestration for chat turns."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
from collections.abc import AsyncIterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError

from src.academic.literature.index_service import IndexService
from src.academic.services import ArtifactService, PaperService, WorkspaceService
from src.agents.memory.capture import enqueue_memory_capture
from src.agents.middlewares.thread_data import get_thread_data_root
from src.application.errors import ApplicationError, BadRequestError, NotFoundError, PaymentRequiredError
from src.application.results import (
    ChatTurnAttachment,
    ChatTurnRequest,
    CompletedChatTurn,
    GeneratedChatReply,
    PreparedChatTurn,
)
from src.config import get_model_config
from src.config.config_loader import get_app_config
from src.config.llm_config import LLMSettings
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


def _model_supports_streaming(model_name: str) -> bool:
    """Infer whether the selected chat model supports token streaming."""
    try:
        model_config = get_model_config(model_name)
    except Exception:
        model_config = None

    supports_streaming = getattr(model_config, "supports_streaming", None)
    if isinstance(supports_streaming, bool):
        return supports_streaming
    return True


def _subagent_runtime_defaults() -> tuple[bool, int]:
    """Load chat-side subagent defaults from app config."""
    try:
        subagents = get_app_config().subagents
        return bool(subagents.enabled), int(subagents.max_concurrent)
    except Exception:
        return True, 3


def _resolve_workspace_id(request: ChatTurnRequest, thread: ChatThread) -> str | None:
    return request.workspace_id or thread.workspace_id


def _serialize_structured_hint(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _stringify_persisted_user_message_content(
    message: Mapping[str, Any],
    *,
    include_feature_seed: bool = True,
) -> str:
    content = str(message.get("content") or "").strip()
    if not include_feature_seed:
        return content

    metadata = message.get("metadata")
    if not isinstance(metadata, Mapping):
        return content

    orchestration = metadata.get("orchestration")
    if not isinstance(orchestration, Mapping):
        return content

    feature_id = str(orchestration.get("feature_id") or "").strip()
    params = orchestration.get("params")
    if not feature_id:
        return content

    lines = [
        "<workspace_feature_seed>",
        "以下是 UI 提供的 feature 入口提示：",
        f"- feature_id: {feature_id}",
    ]
    if isinstance(params, Mapping) and params:
        lines.append(f"- params: {_serialize_structured_hint(dict(params))}")
    lines.extend(
        [
            "这只是辅助上下文，不是必须立即执行的命令。",
            "请先结合用户本轮真实意图，再决定是否调用 `run_workspace_feature`。",
            "</workspace_feature_seed>",
        ]
    )
    structured_context = "\n".join(lines)
    if content:
        return f"{content}\n\n{structured_context}"
    return structured_context


def _stringify_persisted_message_content(message: Mapping[str, Any]) -> str:
    role = str(message.get("role") or "").strip()
    content = str(message.get("content") or "").strip()

    if role == "user":
        return _stringify_persisted_user_message_content(message)

    if role != "assistant":
        return content

    additions: list[str] = []
    metadata = message.get("metadata")
    if isinstance(metadata, Mapping):
        orchestration = metadata.get("orchestration")
        if isinstance(orchestration, Mapping):
            feature_id = orchestration.get("feature_id")
            status = orchestration.get("status")
            task_id = orchestration.get("task_id")
            fields = [
                f"feature={feature_id}" if feature_id else None,
                f"status={status}" if status else None,
                f"task_id={task_id}" if task_id else None,
            ]
            summary = ", ".join(field for field in fields if field)
            if summary:
                additions.append(f"[orchestration: {summary}]")

    blocks = message.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, Mapping):
                continue
            block_type = str(block.get("type") or "").strip().lower()
            data = block.get("data")
            if block_type == "task" and isinstance(data, Mapping):
                title = str(block.get("title") or "task").strip()
                task_id = data.get("task_id")
                status = data.get("status")
                note = ", ".join(
                    part
                    for part in [
                        f"title={title}" if title else None,
                        f"task_id={task_id}" if task_id else None,
                        f"status={status}" if status else None,
                    ]
                    if part
                )
                if note:
                    additions.append(f"[task: {note}]")
            elif block_type == "result" and isinstance(data, Mapping):
                summary = data.get("summary")
                if isinstance(summary, str) and summary.strip():
                    additions.append(f"[result: {summary.strip()}]")
            elif block_type == "warning" and isinstance(data, Mapping):
                detail = data.get("detail")
                if isinstance(detail, str) and detail.strip():
                    additions.append(f"[warning: {detail.strip()}]")

    if not additions:
        return content

    structured_context = "\n".join(additions)
    if content:
        return f"{content}\n\n{structured_context}"
    return structured_context


def _build_langchain_messages(thread: ChatThread) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    raw_messages = list(thread.messages or [])
    latest_user_idx = max(
        (
            index
            for index, msg in enumerate(raw_messages)
            if isinstance(msg, Mapping) and msg.get("role") == "user"
        ),
        default=-1,
    )
    for index, msg in enumerate(raw_messages):
        if msg["role"] == "user":
            messages.append(
                HumanMessage(
                    content=_stringify_persisted_user_message_content(
                        msg,
                        include_feature_seed=index == latest_user_idx,
                    )
                )
            )
        elif msg["role"] == "assistant":
            messages.append(
                AIMessage(content=_stringify_persisted_message_content(msg))
            )
        elif msg["role"] == "system":
            messages.append(SystemMessage(content=str(msg.get("content") or "")))
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


def _extract_reasoning_text_from_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if isinstance(payload, Mapping):
        direct_text = payload.get("text")
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text.strip()

        summary = payload.get("summary")
        if isinstance(summary, list):
            summary_text = "\n".join(
                text.strip()
                for item in summary
                if isinstance(item, Mapping)
                and isinstance((text := item.get("text")), str)
                and text.strip()
            )
            if summary_text:
                return summary_text

        details = payload.get("reasoning_details")
        if isinstance(details, list):
            detail_text = "\n".join(
                text.strip()
                for item in details
                if isinstance(item, Mapping)
                and isinstance((text := item.get("text")), str)
                and text.strip()
            )
            if detail_text:
                return detail_text

        nested_content = payload.get("content")
        if isinstance(nested_content, list):
            nested_text = "\n".join(
                text
                for block in nested_content
                if isinstance(block, Mapping)
                and isinstance((text := _extract_reasoning_text_from_block(block)), str)
                and text
            )
            if nested_text:
                return nested_text

    return ""


def _extract_reasoning_text_from_block(block: Mapping[str, Any]) -> str:
    block_type = str(block.get("type") or "").lower()
    if block_type not in {"reasoning", "thinking", "reasoning_content"}:
        return ""
    return _extract_reasoning_text_from_payload(block)


def _extract_reasoning_text(message: Any) -> str:
    reasoning_details = getattr(message, "reasoning_details", None)
    reasoning_details_text = _extract_reasoning_text_from_payload(reasoning_details)
    if reasoning_details_text:
        return reasoning_details_text

    additional_kwargs = getattr(message, "additional_kwargs", None)
    if isinstance(additional_kwargs, Mapping):
        reasoning = additional_kwargs.get("reasoning")
        reasoning_text = _extract_reasoning_text_from_payload(reasoning)
        if reasoning_text:
            return reasoning_text
        reasoning_details = additional_kwargs.get("reasoning_details")
        reasoning_details_text = _extract_reasoning_text_from_payload(reasoning_details)
        if reasoning_details_text:
            return reasoning_details_text

    response_metadata = getattr(message, "response_metadata", None)
    if isinstance(response_metadata, Mapping):
        reasoning_text = _extract_reasoning_text_from_payload(response_metadata.get("reasoning"))
        if reasoning_text:
            return reasoning_text
        reasoning_details_text = _extract_reasoning_text_from_payload(
            response_metadata.get("reasoning_details")
        )
        if reasoning_details_text:
            return reasoning_details_text

    content = getattr(message, "content", None)
    if isinstance(content, list):
        block_text = "\n".join(
            text
            for block in content
            if isinstance(block, Mapping)
            and isinstance((text := _extract_reasoning_text_from_block(block)), str)
            and text
        )
        if block_text:
            return block_text

    if isinstance(message, Mapping):
        reasoning_text = _extract_reasoning_text_from_payload(message.get("reasoning"))
        if reasoning_text:
            return reasoning_text
        reasoning_details_text = _extract_reasoning_text_from_payload(
            message.get("reasoning_details")
        )
        if reasoning_details_text:
            return reasoning_details_text

    return ""


def _build_reasoning_block(reasoning_text: str) -> dict[str, Any]:
    return {
        "type": "reasoning",
        "title": "思考过程",
        "data": {"text": reasoning_text},
    }


def _reply_reasoning_text(reply: GeneratedChatReply) -> str:
    blocks = reply.blocks if isinstance(reply.blocks, list) else []
    for block in blocks:
        if not isinstance(block, Mapping) or block.get("type") != "reasoning":
            continue
        data = block.get("data")
        if isinstance(data, Mapping):
            text = data.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()

    metadata = reply.metadata if isinstance(reply.metadata, Mapping) else {}
    reasoning = metadata.get("reasoning")
    if isinstance(reasoning, Mapping):
        text = reasoning.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    return ""


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


def _build_recursion_guard_reply(
    *,
    request: ChatTurnRequest,
) -> GeneratedChatReply:
    """Build a deterministic fallback reply when the graph tool-loop guard is hit."""
    feature_id: str | None = None
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    orchestration = metadata.get("orchestration")
    if isinstance(orchestration, Mapping):
        raw_feature_id = orchestration.get("feature_id")
        if isinstance(raw_feature_id, str) and raw_feature_id.strip():
            feature_id = raw_feature_id.strip()

    base_content = (
        "我检测到本轮出现了重复工具调用，已主动停止以避免卡住。"
        " 请明确下一步：如果要执行该功能，请直接回复“开始吧”；"
        " 如果暂不执行，请告诉我你希望先分析的内容。"
    )
    reply_metadata: dict[str, Any] = {"guard": "graph_recursion_fallback"}
    if feature_id:
        reply_metadata["orchestration"] = {
            "mode": "feature_execution",
            "feature_id": feature_id,
            "status": "awaiting_user_confirmation",
        }
    return GeneratedChatReply(content=base_content, metadata=reply_metadata)


def _reply_from_agent_result(
    result: dict[str, Any],
    *,
    thread_id: str,
) -> GeneratedChatReply:
    messages = list(result.get("messages") or [])
    content = ""
    reasoning_text = ""
    if messages:
        content = _coerce_message_content(getattr(messages[-1], "content", ""))
        reasoning_text = _extract_reasoning_text(messages[-1])

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
    if reasoning_text:
        metadata["reasoning"] = {"text": reasoning_text}
        if not any(
            isinstance(block, dict) and block.get("type") == "reasoning"
            for block in blocks
        ):
            blocks.insert(0, _build_reasoning_block(reasoning_text))

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


def _stream_deltas_from_chunk(
    chunk: Any,
    metadata: Mapping[str, Any] | None = None,
) -> list[ChatStreamDelta]:
    if isinstance(metadata, Mapping):
        langgraph_node = metadata.get("langgraph_node")
        if langgraph_node and langgraph_node != "agent":
            return []

    deltas: list[ChatStreamDelta] = []
    reasoning_text = _extract_reasoning_text(chunk)
    if reasoning_text:
        deltas.append(ChatStreamDelta(kind="reasoning", text=reasoning_text))

    content = getattr(chunk, "content", chunk)
    content_text = _coerce_message_content(content)
    if content_text:
        deltas.append(ChatStreamDelta(kind="content", text=content_text))

    return deltas


@dataclass(slots=True)
class _ChatAgentRuntime:
    workspace_id: str | None
    effective_skill: str | None
    effective_model: str
    config: RunnableConfig
    initial_state: dict[str, object]
    middlewares: list[Any]


@dataclass(frozen=True, slots=True)
class ChatStreamDelta:
    kind: Literal["reasoning", "content"]
    text: str


class _ReplyStreamRun:
    """Async iterator wrapper that exposes the completed reply."""

    def __init__(
        self,
        iterator: AsyncIterator[ChatStreamDelta],
        reply_future: asyncio.Future[GeneratedChatReply],
    ) -> None:
        self._iterator = iterator
        self._reply_future = reply_future

    def __aiter__(self) -> AsyncIterator[ChatStreamDelta]:
        return self._iterator

    async def wait_reply(self) -> GeneratedChatReply:
        return await self._reply_future


class _CompletedTurnStreamRun:
    """Async iterator wrapper that exposes the completed chat turn."""

    def __init__(
        self,
        iterator: AsyncIterator[ChatStreamDelta],
        completed_future: asyncio.Future[CompletedChatTurn],
    ) -> None:
        self._iterator = iterator
        self._completed_future = completed_future

    def __aiter__(self) -> AsyncIterator[ChatStreamDelta]:
        return self._iterator

    async def wait_completed(self) -> CompletedChatTurn:
        return await self._completed_future


class ChatTurnHandler:
    """Application-layer orchestration for one chat turn."""

    def __init__(
        self,
        *,
        chat_thread_service: ChatThreadService,
        workspace_service: WorkspaceService | None = None,
        index_service: IndexService | None = None,
        artifact_service: ArtifactService | None = None,
        paper_service: PaperService | None = None,
    ) -> None:
        self.chat_thread_service = chat_thread_service
        self.workspace_service = workspace_service
        self.index_service = index_service
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
        if isinstance(request.metadata, dict) and request.metadata:
            metadata.update(request.metadata)
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
        except asyncio.CancelledError:
            await self._fail_chat_turn(thread)
            raise
        except Exception:
            await self._fail_chat_turn(thread)
            raise

        return await self._finalize_generated_reply(
            prepared,
            actor_id=actor_id,
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

    def stream_turn(
        self,
        prepared: PreparedChatTurn,
        *,
        actor_id: str,
    ) -> _CompletedTurnStreamRun:
        completed_future: asyncio.Future[CompletedChatTurn] = (
            asyncio.get_running_loop().create_future()
        )

        async def _iterator() -> AsyncIterator[ChatStreamDelta]:
            reply_stream = None
            try:
                reply_stream = self._stream_chat_response(
                    prepared.request,
                    prepared.thread,
                    actor_id=actor_id,
                )
                async for delta in reply_stream:
                    if delta.text:
                        yield delta
                reply = await reply_stream.wait_reply()
                completed = await self._finalize_generated_reply(
                    prepared,
                    actor_id=actor_id,
                    reply=reply,
                )
                if not completed_future.done():
                    completed_future.set_result(completed)
            except asyncio.CancelledError as exc:
                await self._fail_chat_turn(prepared.thread)
                if not completed_future.done():
                    completed_future.set_exception(exc)
                raise
            except Exception as exc:
                if reply_stream is not None:
                    try:
                        await reply_stream.wait_reply()
                    except Exception:
                        pass
                await self._fail_chat_turn(prepared.thread)
                if not completed_future.done():
                    completed_future.set_exception(exc)
                raise

        return _CompletedTurnStreamRun(_iterator(), completed_future)

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

    async def _finalize_generated_reply(
        self,
        prepared: PreparedChatTurn,
        *,
        actor_id: str,
        reply: GeneratedChatReply,
    ) -> CompletedChatTurn:
        request = prepared.request
        thread = prepared.thread
        billing_metadata: dict[str, Any] | None = None

        try:
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
        except asyncio.CancelledError:
            await self._refund_chat_turn_billing(
                actor_id=actor_id,
                billing_metadata=billing_metadata,
            )
            await self._fail_chat_turn(thread)
            raise
        except Exception:
            await self._refund_chat_turn_billing(
                actor_id=actor_id,
                billing_metadata=billing_metadata,
            )
            await self._fail_chat_turn(thread)
            raise

        return CompletedChatTurn(
            thread=thread,
            assistant_message=dict(assistant_message),
            reply=reply,
        )

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
            index_service=self.index_service,
            artifact_service=self.artifact_service,
            paper_service=self.paper_service,
        )

    def _stream_chat_response(
        self,
        request: ChatTurnRequest,
        thread: ChatThread,
        *,
        actor_id: str,
    ) -> _ReplyStreamRun:
        return stream_chat_response(
            request,
            thread,
            actor_id=actor_id,
            workspace_service=self.workspace_service,
            index_service=self.index_service,
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


def _build_chat_agent_runtime(
    request: ChatTurnRequest,
    thread: ChatThread,
    *,
    actor_id: str,
    workspace_service: WorkspaceService | None = None,
    index_service: IndexService | None = None,
    artifact_service: ArtifactService | None = None,
    paper_service: PaperService | None = None,
) -> _ChatAgentRuntime:
    from src.agents.lead_agent.agent import build_pipeline

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
        index_service=index_service,
        artifact_service=artifact_service,
        paper_service=paper_service,
        memory_capture_enabled=False,
    )
    return _ChatAgentRuntime(
        workspace_id=workspace_id,
        effective_skill=effective_skill,
        effective_model=effective_model,
        config=config,
        initial_state=initial_state,
        middlewares=middlewares,
    )


async def generate_chat_response(
    request: ChatTurnRequest,
    thread: ChatThread,
    *,
    actor_id: str,
    workspace_service: WorkspaceService | None = None,
    index_service: IndexService | None = None,
    artifact_service: ArtifactService | None = None,
    paper_service: PaperService | None = None,
) -> GeneratedChatReply:
    """Generate a chat response through the unified lead-agent pipeline."""
    from src.agents.lead_agent.agent import make_lead_agent

    runtime = _build_chat_agent_runtime(
        request,
        thread,
        actor_id=actor_id,
        workspace_service=workspace_service,
        index_service=index_service,
        artifact_service=artifact_service,
        paper_service=paper_service,
    )

    await ensure_chat_turn_budget(actor_id)
    agent = cast(Any, make_lead_agent(runtime.config, middlewares=runtime.middlewares))
    try:
        result = await asyncio.wait_for(
            agent.ainvoke(runtime.initial_state, config=runtime.config),
            timeout=LLMSettings.AGENT_TIMEOUT,
        )
    except GraphRecursionError:
        logger.warning(
            "Agent recursion guard triggered for thread %s; returning fallback reply",
            thread.id,
        )
        return _build_recursion_guard_reply(request=request)
    except TimeoutError as exc:
        logger.error(
            "Agent timed out after %.0fs for thread %s",
            LLMSettings.AGENT_TIMEOUT,
            thread.id,
        )
        raise ApplicationError("AI 响应超时，请稍后重试或简化您的问题。") from exc

    reply = _reply_from_agent_result(result, thread_id=thread.id)
    return _attach_usage_metadata(
        reply,
        extract_usage_from_agent_result(result),
        model_name=runtime.effective_model,
        source="chat_agent",
    )


def stream_chat_response(
    request: ChatTurnRequest,
    thread: ChatThread,
    *,
    actor_id: str,
    workspace_service: WorkspaceService | None = None,
    index_service: IndexService | None = None,
    artifact_service: ArtifactService | None = None,
    paper_service: PaperService | None = None,
) -> _ReplyStreamRun:
    """Stream a chat response while still returning the final structured reply."""
    from src.agents.lead_agent.agent import make_lead_agent

    runtime = _build_chat_agent_runtime(
        request,
        thread,
        actor_id=actor_id,
        workspace_service=workspace_service,
        index_service=index_service,
        artifact_service=artifact_service,
        paper_service=paper_service,
    )
    reply_future: asyncio.Future[GeneratedChatReply] = asyncio.get_running_loop().create_future()

    async def _iterator() -> AsyncIterator[ChatStreamDelta]:
        accumulated_reasoning = ""
        try:
            await ensure_chat_turn_budget(actor_id)
            agent = cast(
                Any,
                make_lead_agent(runtime.config, middlewares=runtime.middlewares),
            )

            if not _model_supports_streaming(runtime.effective_model):
                try:
                    result = await asyncio.wait_for(
                        agent.ainvoke(
                            runtime.initial_state,
                            config=runtime.config,
                        ),
                        timeout=LLMSettings.AGENT_TIMEOUT,
                    )
                except GraphRecursionError:
                    logger.warning(
                        "Agent recursion guard triggered for thread %s (non-streaming model)",
                        thread.id,
                    )
                    reply = _build_recursion_guard_reply(request=request)
                    if reply.content:
                        yield ChatStreamDelta(kind="content", text=reply.content)
                    if not reply_future.done():
                        reply_future.set_result(reply)
                    return
                reply = _attach_usage_metadata(
                    _reply_from_agent_result(result, thread_id=thread.id),
                    extract_usage_from_agent_result(result),
                    model_name=runtime.effective_model,
                    source="chat_agent",
                )
                reasoning_text = _reply_reasoning_text(reply)
                if reasoning_text:
                    yield ChatStreamDelta(kind="reasoning", text=reasoning_text)
                if reply.content:
                    yield ChatStreamDelta(kind="content", text=reply.content)
                if not reply_future.done():
                    reply_future.set_result(reply)
                return

            stream_run = agent.astream_with_result(
                runtime.initial_state,
                config=runtime.config,
                stream_mode=["messages", "values"],
            )
            async with asyncio.timeout(LLMSettings.AGENT_TIMEOUT):
                async for mode, payload in stream_run:
                    if mode != "messages":
                        continue
                    chunk, metadata = payload
                    for delta in _stream_deltas_from_chunk(chunk, metadata):
                        if delta.kind == "reasoning":
                            if delta.text.startswith(accumulated_reasoning):
                                normalized_text = delta.text[len(accumulated_reasoning) :]
                                accumulated_reasoning = delta.text
                            elif delta.text in accumulated_reasoning:
                                normalized_text = ""
                            else:
                                accumulated_reasoning += delta.text
                                normalized_text = delta.text
                            if normalized_text:
                                yield ChatStreamDelta(
                                    kind="reasoning",
                                    text=normalized_text,
                                )
                            continue
                        if delta.text:
                            yield delta
                try:
                    result = await stream_run.result()
                except GraphRecursionError:
                    logger.warning(
                        "Agent recursion guard triggered for thread %s (stream result)",
                        thread.id,
                    )
                    reply = _build_recursion_guard_reply(request=request)
                    if reply.content:
                        yield ChatStreamDelta(kind="content", text=reply.content)
                    if not reply_future.done():
                        reply_future.set_result(reply)
                    return

            reply = _attach_usage_metadata(
                _reply_from_agent_result(result, thread_id=thread.id),
                extract_usage_from_agent_result(result),
                model_name=runtime.effective_model,
                source="chat_agent",
            )
            if not reply_future.done():
                reply_future.set_result(reply)
        except TimeoutError:
            logger.error(
                "Streaming agent timed out after %.0fs for thread %s",
                LLMSettings.AGENT_TIMEOUT,
                thread.id,
            )
            exc = ApplicationError("AI 响应超时，请稍后重试或简化您的问题。")
            if not reply_future.done():
                reply_future.set_exception(exc)
            raise
        except Exception as exc:
            if not reply_future.done():
                reply_future.set_exception(exc)
            raise

    return _ReplyStreamRun(_iterator(), reply_future)
