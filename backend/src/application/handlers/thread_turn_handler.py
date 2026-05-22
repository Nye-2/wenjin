"""Application-layer orchestration for thread turns."""

from __future__ import annotations

import asyncio
import ast
import base64
import inspect
import json
import logging
import mimetypes
import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError

from src.academic.services.artifact_service import ArtifactService
from src.academic.services.workspace_service import WorkspaceService
from src.agents.middlewares.thread_data import get_thread_data_root
from src.application.errors import ApplicationError, BadRequestError, NotFoundError, PaymentRequiredError
from src.application.results import (
    CompletedThreadTurn,
    GeneratedThreadReply,
    PreparedThreadTurn,
    ThreadTurnAttachment,
    ThreadTurnRequest,
)
from src.config import get_model_config
from src.config.config_loader import get_app_config
from src.config.llm_config import LLMSettings
from src.database import get_db_session
from src.models import model_supports_vision, route_chat_model
from src.models.router import InvalidRequestedModelError
from src.services import ThreadAccessError, ThreadService
from src.services.credit_service import CreditService
from src.services.memory_capture_service import get_memory_capture_service
from src.services.thread_billing import (
    extract_usage_from_agent_result,
    normalize_token_usage,
    usage_to_metadata,
)
from src.services.thread_events import publish_thread_updated, set_thread_status
from src.tools.builtins.artifacts import (
    build_presented_artifact_items,
    build_presented_artifacts_block,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.database import Thread

_THREAD_VIRTUAL_ROOT = "/mnt/user-data/"
_THREAD_UPLOADS_VIRTUAL_ROOT = "/mnt/user-data/uploads/"
_MEMORY_CAPTURE_MAX_MESSAGE_CHARS = 2200
_MAX_VIEWED_IMAGE_BYTES = 5 * 1024 * 1024
_EXECUTION_ID_RECEIPT_RE = re.compile(
    r"(?:执行\s*ID|execution[\s_-]*id)\s*[:：]?\s*"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_LAUNCH_RECEIPT_RE = re.compile(
    r"(?:已(?:经)?(?:为你)?启动|已发起|开始执行|正在执行|launched|started)",
    re.IGNORECASE,
)


def _model_supports_streaming(model_name: str) -> bool:
    """Infer whether the selected thread model supports token streaming."""
    try:
        model_config = get_model_config(model_name)
    except Exception:
        model_config = None

    supports_streaming = getattr(model_config, "supports_streaming", None)
    if isinstance(supports_streaming, bool):
        return supports_streaming
    return True


def _resolve_workspace_id(request: ThreadTurnRequest, thread: Thread) -> str | None:
    return thread.workspace_id or request.workspace_id


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[: max(0, max_chars - 1)].rstrip()
    return f"{truncated}…"


def _extract_launch_feature_params_from_metadata(
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    orchestration = metadata.get("orchestration")
    if not isinstance(orchestration, Mapping):
        return {}
    params = orchestration.get("params")
    if not isinstance(params, Mapping):
        return {}

    reserved_keys = {"entry", "execution_id", "follow_up_prompt"}
    normalized: dict[str, Any] = {}
    for key, value in params.items():
        if not isinstance(key, str) or key in reserved_keys:
            continue
        normalized[key] = value
    return normalized


def _stringify_persisted_message_content(message: Mapping[str, Any]) -> str:
    role = str(message.get("role") or "").strip()
    content = str(message.get("content") or "").strip()

    if role not in {"user", "assistant"}:
        return content

    additions: list[str] = []
    metadata = message.get("metadata")
    if isinstance(metadata, Mapping):
        orchestration = metadata.get("orchestration")
        if isinstance(orchestration, Mapping):
            feature_id = orchestration.get("feature_id")
            execution_id = orchestration.get("execution_id")

            if role == "assistant":
                status = orchestration.get("status")
                task_id = orchestration.get("task_id")
                fields = [
                    f"feature={feature_id}" if feature_id else None,
                    f"status={status}" if status else None,
                    f"task_id={task_id}" if task_id else None,
                    f"execution_id={execution_id}" if execution_id else None,
                ]
                summary = ", ".join(field for field in fields if field)
                if summary:
                    additions.append(f"[orchestration: {summary}]")
            else:
                block_action = metadata.get("block_action")
                should_surface_orchestration = bool(execution_id) or isinstance(
                    block_action, Mapping
                )
                if should_surface_orchestration:
                    fields = [
                        f"feature={feature_id}" if feature_id else None,
                        f"execution_id={execution_id}" if execution_id else None,
                    ]
                    summary = ", ".join(field for field in fields if field)
                    if summary:
                        additions.append(f"[orchestration: {summary}]")

        if role == "user":
            block_action = metadata.get("block_action")
            if isinstance(block_action, Mapping):
                action = block_action.get("action")
                intent = block_action.get("intent")
                source_block_kind = block_action.get("source_block_kind")
                fields = [
                    f"action={action}" if action else None,
                    f"intent={intent}" if intent else None,
                    f"source={source_block_kind}" if source_block_kind else None,
                ]
                summary = ", ".join(field for field in fields if field)
                if summary:
                    additions.append(f"[thread_action: {summary}]")

    if role == "assistant":
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
                    result_summary = data.get("summary")
                    if isinstance(result_summary, str) and result_summary.strip():
                        additions.append(f"[result: {result_summary.strip()}]")
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


def _build_langchain_messages(persisted_messages: list[Mapping[str, Any]]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for msg in persisted_messages:
        role = str(msg.get("role") or "").strip()
        if role == "user":
            messages.append(
                HumanMessage(content=_stringify_persisted_message_content(msg))
            )
        elif role == "assistant":
            additional_kwargs: dict[str, Any] = {}
            reasoning_text = _extract_reasoning_text(msg)
            if reasoning_text:
                additional_kwargs["reasoning"] = reasoning_text
                additional_kwargs["reasoning_content"] = reasoning_text
            messages.append(
                AIMessage(
                    content=_stringify_persisted_message_content(msg),
                    additional_kwargs=additional_kwargs,
                )
            )
        elif role == "system":
            messages.append(SystemMessage(content=str(msg.get("content") or "")))
    return messages


def build_thread_runtime_config(
    *,
    request: ThreadTurnRequest,
    thread: Thread,
    actor_id: str,
    workspace_id: str | None,
    effective_skill: str | None,
    effective_model: str,
    execution_id: str | None = None,
) -> RunnableConfig:
    configurable: dict[str, Any] = {
        "thread_id": thread.id,
        "workspace_id": workspace_id,
        "user_id": actor_id,
        "model_name": effective_model,
        "supports_vision": model_supports_vision(effective_model),
        "selected_skill": effective_skill,
        "thinking_enabled": request.thinking_enabled,
        "reasoning_effort": request.reasoning_effort,
    }
    launch_feature_params = _extract_launch_feature_params_from_metadata(request.metadata)
    if launch_feature_params:
        configurable["launch_feature_params"] = launch_feature_params
    if execution_id is not None:
        configurable["execution_id"] = execution_id
    return {"configurable": configurable}


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


def _attachment_state_for_thread_turn(
    *,
    thread_id: str,
    attachments: tuple[ThreadTurnAttachment, ...],
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
                "reference_id": attachment.reference_id,
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
            file_size = actual_path.stat().st_size
        except OSError:
            logger.debug("Failed to stat uploaded image attachment: %s", actual_path, exc_info=True)
            continue

        if file_size > _MAX_VIEWED_IMAGE_BYTES:
            logger.debug(
                "Skipping oversized uploaded image attachment for thread state: %s (%s bytes)",
                actual_path,
                file_size,
            )
            continue

        try:
            image_bytes = actual_path.read_bytes()
            if len(image_bytes) > _MAX_VIEWED_IMAGE_BYTES:
                logger.debug(
                    "Skipping oversized uploaded image attachment after read: %s (%s bytes)",
                    actual_path,
                    len(image_bytes),
                )
                continue
            viewed_images[path] = {
                "base64": base64.b64encode(image_bytes).decode("utf-8"),
                "mime_type": effective_mime,
            }
        except OSError:
            logger.debug("Failed to load uploaded image attachment: %s", actual_path, exc_info=True)

    return uploaded_files, viewed_images


def build_thread_initial_state(
    thread: Thread,
    *,
    actor_id: str,
    workspace_id: str | None,
    effective_skill: str | None,
    attachments: tuple[ThreadTurnAttachment, ...],
    conversation_messages: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    initial_state: dict[str, object] = {
        "messages": _build_langchain_messages(list(conversation_messages or [])),
        "thread_id": str(thread.id),
        "user_id": actor_id,
        "workspace_id": workspace_id,
        "current_skill": effective_skill,
    }
    uploaded_files, viewed_images = _attachment_state_for_thread_turn(
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
        metadata = message.get("metadata")
        if isinstance(metadata, Mapping):
            reasoning_text = _extract_reasoning_text_from_payload(metadata.get("reasoning"))
            if reasoning_text:
                return reasoning_text
            reasoning_details_text = _extract_reasoning_text_from_payload(
                metadata.get("reasoning_details")
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


def _reply_reasoning_text(reply: GeneratedThreadReply) -> str:
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
    reply: GeneratedThreadReply,
    usage: Any,
    *,
    model_name: str | None,
    source: str,
) -> GeneratedThreadReply:
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


def _extract_forward_safe_orchestration_metadata(
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}

    orchestration = metadata.get("orchestration")
    if not isinstance(orchestration, Mapping):
        return {}

    forwarded: dict[str, Any] = {}
    feature_id = orchestration.get("feature_id")
    if isinstance(feature_id, str) and feature_id.strip():
        forwarded["feature_id"] = feature_id.strip()

    params = orchestration.get("params")
    if isinstance(params, Mapping) and params:
        forwarded["params"] = dict(params)

    return forwarded


def _normalize_reply_orchestration_metadata(
    reply: GeneratedThreadReply,
    *,
    request_metadata: Mapping[str, Any] | None = None,
    execution_id: str | None = None,
) -> GeneratedThreadReply:
    """Ensure assistant replies persist canonical execution linkage."""
    forwarded = _extract_forward_safe_orchestration_metadata(request_metadata)
    if not execution_id and not forwarded:
        return reply

    reply.metadata = dict(reply.metadata or {})
    existing = reply.metadata.get("orchestration")
    orchestration = dict(existing) if isinstance(existing, Mapping) else {}
    if not orchestration.get("feature_id") and forwarded.get("feature_id"):
        orchestration["feature_id"] = forwarded["feature_id"]
    if not orchestration.get("params") and forwarded.get("params"):
        orchestration["params"] = forwarded["params"]
    if not orchestration.get("execution_id"):
        orchestration["execution_id"] = execution_id
    if orchestration:
        reply.metadata["orchestration"] = orchestration
    return reply


def _build_incremental_memory_capture_messages(
    *,
    user_message: str,
    assistant_message: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Build a compact per-turn capture payload for long-term memory extraction."""
    capture_messages: list[dict[str, str]] = []

    normalized_user = _truncate_text(str(user_message or "").strip(), _MEMORY_CAPTURE_MAX_MESSAGE_CHARS)
    if normalized_user:
        capture_messages.append({"role": "user", "content": normalized_user})

    assistant_text = _truncate_text(
        _stringify_persisted_message_content(assistant_message).strip(),
        _MEMORY_CAPTURE_MAX_MESSAGE_CHARS,
    )
    if assistant_text:
        capture_messages.append({"role": "assistant", "content": assistant_text})

    return capture_messages


def _build_recursion_guard_reply(
    *,
    request: ThreadTurnRequest,
) -> GeneratedThreadReply:
    """Build a deterministic fallback reply when the graph tool-loop guard is hit."""
    base_content = (
        "我检测到本轮出现了重复工具调用，已主动停止以避免卡住。"
        " 请简化你的问题，或明确希望我先分析哪一部分。"
    )
    reply_metadata: dict[str, Any] = {"guard": "graph_recursion_fallback"}
    return GeneratedThreadReply(content=base_content, metadata=reply_metadata)


def _looks_like_unbacked_launch_receipt(content: str) -> bool:
    normalized = content.strip()
    if not normalized:
        return False
    return bool(
        _EXECUTION_ID_RECEIPT_RE.search(normalized)
        or (
            _LAUNCH_RECEIPT_RE.search(normalized)
            and ("launch_feature" in normalized or "执行" in normalized or "任务" in normalized)
        )
    )


def _build_unbacked_launch_receipt_guard_reply() -> GeneratedThreadReply:
    return GeneratedThreadReply(
        content=(
            "本轮没有成功启动该能力：系统没有收到真实的 launch_feature 工具结果。"
            " 请重新发起该能力。"
        ),
        blocks=[
            {
                "type": "warning",
                "title": "能力未启动",
                "data": {
                    "code": "unbacked_launch_receipt",
                    "detail": "Agent 文本声称已启动能力，但消息链中没有 launch_feature 工具调用结果。",
                },
            }
        ],
        metadata={"guard": "unbacked_launch_receipt"},
    )


def _reply_from_agent_result(
    result: dict[str, Any],
    *,
    thread_id: str,
) -> GeneratedThreadReply:
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
    launch_blocks = _extract_launch_feature_blocks(messages)
    if launch_blocks:
        blocks = [*launch_blocks, *blocks]
    elif _looks_like_unbacked_launch_receipt(content):
        return _build_unbacked_launch_receipt_guard_reply()
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

    return GeneratedThreadReply(
        content=content,
        blocks=blocks,
        metadata=metadata,
    )


def _coerce_tool_result_payload(content: Any) -> dict[str, Any] | None:
    if isinstance(content, Mapping):
        return {str(key): value for key, value in content.items()}
    if isinstance(content, list):
        for item in content:
            if isinstance(item, Mapping) and item.get("type") == "text":
                payload = _coerce_tool_result_payload(item.get("text"))
                if payload is not None:
                    return payload
        return None
    if not isinstance(content, str) or not content.strip():
        return None

    raw = content.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return None
    if not isinstance(parsed, Mapping):
        return None
    return {str(key): value for key, value in parsed.items()}


def _extract_launch_feature_invocations(message: Any) -> list[dict[str, Any]]:
    raw_tool_calls = getattr(message, "tool_calls", None)
    if not isinstance(raw_tool_calls, list):
        return []

    invocations: list[dict[str, Any]] = []
    for call in raw_tool_calls:
        if not isinstance(call, Mapping):
            continue
        name = str(call.get("name") or "").strip()
        if name != "launch_feature":
            continue
        args = call.get("args")
        invocations.append(
            {
                "tool": name,
                "args": dict(args) if isinstance(args, Mapping) else {},
            }
        )
    return invocations


def _extract_launch_feature_result(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, ToolMessage):
        return None
    payload = _coerce_tool_result_payload(message.content)
    if not payload:
        return None
    if not payload.get("status") or not payload.get("feature_id"):
        return None
    return payload


def _extract_launch_feature_blocks(messages: list[Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    seen_results: set[tuple[str, str]] = set()

    for message in messages:
        for invocation in _extract_launch_feature_invocations(message):
            blocks.append({"kind": "tool_invocation", "data": invocation})

        result = _extract_launch_feature_result(message)
        if result is None:
            continue
        result_key = (
            str(result.get("execution_id") or ""),
            str(result.get("feature_id") or ""),
        )
        if result_key in seen_results:
            continue
        seen_results.add(result_key)
        blocks.append({"kind": "tool_result", "data": result})

    return blocks


def _stream_deltas_from_chunk(
    chunk: Any,
    metadata: Mapping[str, Any] | None = None,
) -> list[ThreadStreamDelta]:
    tool_deltas: list[ThreadStreamDelta] = []
    for invocation in _extract_launch_feature_invocations(chunk):
        tool_deltas.append(ThreadStreamDelta(kind="tool_invocation", data=invocation))
    result = _extract_launch_feature_result(chunk)
    if result is not None:
        tool_deltas.append(ThreadStreamDelta(kind="tool_result", data=result))
    if tool_deltas:
        return tool_deltas

    if isinstance(metadata, Mapping):
        langgraph_node = metadata.get("langgraph_node")
        if langgraph_node and langgraph_node != "agent":
            return []

    deltas: list[ThreadStreamDelta] = []
    reasoning_text = _extract_reasoning_text(chunk)
    if reasoning_text:
        deltas.append(ThreadStreamDelta(kind="reasoning", text=reasoning_text))

    content = getattr(chunk, "content", chunk)
    content_text = _coerce_message_content(content)
    if content_text:
        deltas.append(ThreadStreamDelta(kind="content", text=content_text))

    return deltas


@dataclass(slots=True)
class _ThreadAgentRuntime:
    workspace_id: str | None
    effective_skill: str | None
    effective_model: str
    config: RunnableConfig
    initial_state: dict[str, object]
    middlewares: list[Any]


@dataclass(frozen=True, slots=True)
class ThreadStreamDelta:
    kind: Literal["reasoning", "content", "tool_invocation", "tool_result"]
    text: str = ""
    data: dict[str, Any] | None = None


class _ReplyStreamRun:
    """Async iterator wrapper that exposes the completed reply."""

    def __init__(
        self,
        iterator: AsyncIterator[ThreadStreamDelta],
        reply_future: asyncio.Future[GeneratedThreadReply],
    ) -> None:
        self._iterator = iterator
        self._reply_future = reply_future
        self._reply_future.add_done_callback(self._consume_future_exception)

    def __aiter__(self) -> AsyncIterator[ThreadStreamDelta]:
        return self._iterator

    async def wait_reply(self) -> GeneratedThreadReply:
        return await self._reply_future

    async def aclose(self) -> None:
        closer = getattr(self._iterator, "aclose", None)
        if callable(closer):
            maybe_awaitable = closer()
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable
        if not self._reply_future.done():
            self._reply_future.cancel()

    @staticmethod
    def _consume_future_exception(future: asyncio.Future[GeneratedThreadReply]) -> None:
        if future.cancelled():
            return
        try:
            future.exception()
        except Exception:
            return


class _CompletedTurnStreamRun:
    """Async iterator wrapper that exposes the completed thread turn."""

    def __init__(
        self,
        iterator: AsyncIterator[ThreadStreamDelta],
        completed_future: asyncio.Future[CompletedThreadTurn],
    ) -> None:
        self._iterator = iterator
        self._completed_future = completed_future
        self._completed_future.add_done_callback(self._consume_future_exception)

    def __aiter__(self) -> AsyncIterator[ThreadStreamDelta]:
        return self._iterator

    async def wait_completed(self) -> CompletedThreadTurn:
        return await self._completed_future

    async def aclose(self) -> None:
        closer = getattr(self._iterator, "aclose", None)
        if callable(closer):
            maybe_awaitable = closer()
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable
        if not self._completed_future.done():
            self._completed_future.cancel()

    @staticmethod
    def _consume_future_exception(future: asyncio.Future[CompletedThreadTurn]) -> None:
        if future.cancelled():
            return
        try:
            future.exception()
        except Exception:
            return


class ThreadTurnHandler:
    """Application-layer orchestration for one thread turn."""

    def __init__(
        self,
        *,
        thread_service: ThreadService,
        workspace_service: WorkspaceService | None = None,
        index_service: Any | None = None,
        artifact_service: ArtifactService | None = None,
        reference_service: Any | None = None,
    ) -> None:
        self.thread_service = thread_service
        self.workspace_service = workspace_service
        self.index_service = index_service
        self.artifact_service = artifact_service
        self.reference_service = reference_service

    async def prepare_turn(
        self,
        request: ThreadTurnRequest,
        *,
        actor_id: str,
    ) -> PreparedThreadTurn:
        thread = await self._get_or_create_owned_thread(request, actor_id=actor_id)
        if self._requires_thread_turn_budget(request, thread):
            await ensure_thread_turn_budget(actor_id)

        metadata = {}
        if isinstance(request.metadata, dict) and request.metadata:
            metadata.update(request.metadata)
        if request.attachments:
            metadata["attachments"] = [
                asdict(attachment)
                for attachment in request.attachments
            ]

        await self.thread_service.add_message(
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
            skill_name=None,
        )
        return PreparedThreadTurn(request=request, thread=thread)

    @staticmethod
    def _requires_thread_turn_budget(request: ThreadTurnRequest, thread: Thread) -> bool:
        """Return whether this prepared turn belongs to the pure chat budget.

        With the ChatTurnRouter bypass removed, every chat turn enters lead_agent;
        feature launches happen via the launch_feature tool, not as a separate
        ingress mode. So every turn is treated as a pure chat turn for budgeting.
        """
        return True

    async def _maybe_compact_thread_history(self, thread: Thread) -> None:
        """Durably compact long thread history before building model context."""
        try:
            app_config = get_app_config()
            from src.agents.middlewares.summarization import (
                SummarizationMiddleware,
                resolve_summarization_settings,
            )

            summary_settings = resolve_summarization_settings(app_config.middlewares.summarization)
            if not summary_settings.enabled:
                return
        except Exception:
            logger.debug("Thread compaction skipped because summarization config is invalid", exc_info=True)
            return

        keep_messages = summary_settings.keep_messages
        conversation_messages = await self.thread_service.list_thread_messages(thread)
        messages = _build_langchain_messages(conversation_messages)
        if len(messages) <= keep_messages:
            return

        summarizer = SummarizationMiddleware.from_settings(summary_settings)
        token_count = summarizer.count_tokens(
            messages,
            model_name=str(getattr(thread, "model", "") or "") or None,
        )
        if token_count < summary_settings.trigger_tokens:
            return

        summary = await summarizer.summarize_messages(messages[:-keep_messages])
        if not summary:
            return
        await self.thread_service.compact_messages(
            thread,
            summary=summary,
            keep_messages=keep_messages,
            source_messages=conversation_messages,
        )

    async def complete_turn(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
    ) -> CompletedThreadTurn:
        thread = prepared.thread

        try:
            reply = await self._generate_prepared_reply(
                prepared,
                actor_id=actor_id,
            )
        except asyncio.CancelledError:
            await self._fail_thread_turn(thread)
            raise
        except Exception:
            await self._fail_thread_turn(thread)
            raise

        return await self._finalize_generated_reply(
            prepared,
            actor_id=actor_id,
            reply=reply,
        )

    async def run_turn(
        self,
        request: ThreadTurnRequest,
        *,
        actor_id: str,
    ) -> CompletedThreadTurn:
        prepared = await self.prepare_turn(request, actor_id=actor_id)
        return await self.complete_turn(prepared, actor_id=actor_id)

    async def preflight_stream_turn(
        self,
        request: ThreadTurnRequest,
        *,
        actor_id: str,
    ) -> None:
        """Validate explicit stream thread routing before opening SSE."""
        try:
            self.thread_service.resolve_requested_model(request.model)
        except InvalidRequestedModelError as exc:
            raise BadRequestError(str(exc)) from exc
        if not request.thread_id:
            return
        await self._get_or_create_owned_thread(request, actor_id=actor_id)

    def stream_turn(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
    ) -> _CompletedTurnStreamRun:
        completed_future: asyncio.Future[CompletedThreadTurn] = (
            asyncio.get_running_loop().create_future()
        )

        async def _iterator() -> AsyncIterator[ThreadStreamDelta]:
            reply_stream = None
            try:
                await self._maybe_compact_thread_history(prepared.thread)
                conversation_messages = await self.thread_service.list_thread_messages(prepared.thread)
                reply_stream = self._stream_thread_response(
                    prepared.request,
                    prepared.thread,
                    actor_id=actor_id,
                    execution_id=prepared.request.metadata.get("orchestration", {}).get("execution_id")
                    if isinstance(prepared.request.metadata, dict)
                    else None,
                    conversation_messages=conversation_messages,
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
                await self._fail_thread_turn(prepared.thread)
                if not completed_future.done():
                    completed_future.set_exception(exc)
                raise
            except Exception as exc:
                if reply_stream is not None:
                    try:
                        await reply_stream.wait_reply()
                    except Exception:
                        pass
                await self._fail_thread_turn(prepared.thread)
                if not completed_future.done():
                    completed_future.set_exception(exc)
                raise

        return _CompletedTurnStreamRun(_iterator(), completed_future)

    async def _get_or_create_owned_thread(
        self,
        request: ThreadTurnRequest,
        *,
        actor_id: str,
    ) -> Thread:
        requested_workspace_id = (
            str(request.workspace_id).strip()
            if request.workspace_id is not None
            else ""
        )
        try:
            thread = await self.thread_service.get_or_create_thread(
                thread_id=request.thread_id,
                user_id=actor_id,
                workspace_id=request.workspace_id,
                model=request.model,
                skill=request.skill,
                skill_explicit=request.skill_explicit,
            )
        except ThreadAccessError as exc:
            raise NotFoundError("Thread not found") from exc
        except InvalidRequestedModelError as exc:
            raise BadRequestError(str(exc)) from exc

        thread_workspace_id = (
            str(thread.workspace_id).strip()
            if thread.workspace_id is not None
            else ""
        )
        if (
            requested_workspace_id
            and thread_workspace_id
            and requested_workspace_id != thread_workspace_id
        ):
            raise BadRequestError(
                "Thread does not belong to the requested workspace"
            )
        return thread

    async def _apply_thread_turn_billing(
        self,
        reply: GeneratedThreadReply,
        *,
        actor_id: str,
        thread: Thread,
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
            billing = await credit_service.consume_for_thread_usage(
                user_id=actor_id,
                token_usage=normalized_usage,
                model_name=usage_metadata.get("model_name") if usage_metadata else None,
                workspace_id=thread.workspace_id,
                thread_id=thread.id,
                metadata={
                    "source": (
                        usage_metadata.get("source", "thread")
                        if usage_metadata is not None
                        else "thread"
                    )
                },
            )

        reply.metadata = dict(reply.metadata or {})
        reply.metadata["billing"] = billing.as_metadata()
        return billing.as_metadata()

    async def _finalize_generated_reply(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
        reply: GeneratedThreadReply,
    ) -> CompletedThreadTurn:
        request = prepared.request
        thread = prepared.thread
        billing_metadata: dict[str, Any] | None = None

        try:
            billing_metadata = await self._apply_thread_turn_billing(
                reply,
                actor_id=actor_id,
                thread=thread,
            )
            assistant_message = await self._persist_thread_reply(
                thread=thread,
                actor_id=actor_id,
                user_message=request.message,
                reply=reply,
            )
        except asyncio.CancelledError:
            await self._refund_thread_turn_billing(
                actor_id=actor_id,
                billing_metadata=billing_metadata,
            )
            await self._fail_thread_turn(thread)
            raise
        except Exception:
            await self._refund_thread_turn_billing(
                actor_id=actor_id,
                billing_metadata=billing_metadata,
            )
            await self._fail_thread_turn(thread)
            raise

        return CompletedThreadTurn(
            thread=thread,
            assistant_message=dict(assistant_message),
            reply=reply,
        )

    async def _refund_thread_turn_billing(
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
                reason="线程回复失败退款",
            )

    async def _persist_thread_reply(
        self,
        *,
        thread: Thread,
        actor_id: str,
        user_message: str,
        reply: GeneratedThreadReply,
    ) -> Mapping[str, Any]:
        assistant_message = await self.thread_service.add_message(
            thread,
            role="assistant",
            content=reply.content,
            blocks=reply.blocks,
            metadata=reply.metadata,
        )
        capture_messages = _build_incremental_memory_capture_messages(
            user_message=user_message,
            assistant_message=assistant_message,
        )
        if capture_messages:
            await get_memory_capture_service().capture_messages(
                thread_id=thread.id,
                user_id=actor_id,
                workspace_id=thread.workspace_id,
                messages=capture_messages,
                source="thread.handler",
            )
        await self.thread_service.set_title_if_empty(thread, user_message)
        await publish_thread_updated(thread)
        await set_thread_status(
            thread.workspace_id,
            thread.id,
            status="completed",
            skill=thread.skill,
            skill_name=None,
        )
        return assistant_message

    async def handle_run_interruption(
        self,
        prepared: PreparedThreadTurn,
        *,
        rollback: bool,
    ) -> None:
        """Best-effort cleanup for externally interrupted run execution."""
        thread = prepared.thread
        if rollback:
            try:
                conversation_messages = await self.thread_service.list_thread_messages(thread)
                rolled_back = await self.thread_service.rollback_last_user_message(
                    thread,
                    expected_content=prepared.request.message,
                    source_messages=conversation_messages,
                )
            except Exception:
                logger.warning(
                    "Failed to rollback interrupted turn for thread %s",
                    thread.id,
                    exc_info=True,
                )
            else:
                if rolled_back:
                    await publish_thread_updated(thread)

    async def _fail_thread_turn(self, thread: Thread) -> None:
        await set_thread_status(
            thread.workspace_id,
            thread.id,
            status="failed",
            skill=thread.skill,
            skill_name=None,
        )

    async def _generate_prepared_reply(
        self,
        prepared: PreparedThreadTurn,
        *,
        actor_id: str,
    ) -> GeneratedThreadReply:
        return await self._generate_thread_response(
            prepared.request,
            prepared.thread,
            actor_id=actor_id,
            execution_id=prepared.request.metadata.get("orchestration", {}).get("execution_id")
            if isinstance(prepared.request.metadata, dict)
            else None,
        )

    async def _generate_thread_response(
        self,
        request: ThreadTurnRequest,
        thread: Thread,
        *,
        actor_id: str,
        execution_id: str | None = None,
    ) -> GeneratedThreadReply:
        await self._maybe_compact_thread_history(thread)
        conversation_messages = await self.thread_service.list_thread_messages(thread)
        return await generate_thread_response(
            request,
            thread,
            actor_id=actor_id,
            execution_id=execution_id,
            workspace_service=self.workspace_service,
            index_service=self.index_service,
            artifact_service=self.artifact_service,
            reference_service=self.reference_service,
            conversation_messages=conversation_messages,
            budget_checked=True,
        )

    def _stream_thread_response(
        self,
        request: ThreadTurnRequest,
        thread: Thread,
        *,
        actor_id: str,
        execution_id: str | None = None,
        conversation_messages: list[dict[str, Any]] | None = None,
    ) -> _ReplyStreamRun:
        return stream_thread_response(
            request,
            thread,
            actor_id=actor_id,
            execution_id=execution_id,
            workspace_service=self.workspace_service,
            index_service=self.index_service,
            artifact_service=self.artifact_service,
            reference_service=self.reference_service,
            conversation_messages=conversation_messages,
            budget_checked=True,
        )


async def ensure_thread_turn_budget(actor_id: str) -> None:
    """Reject pure thread turns once free quota is exhausted and credits are empty."""
    async with get_db_session() as db:
        credit_service = CreditService(db)
        allowed = await credit_service.can_start_thread_turn(actor_id)
        if allowed:
            return
        policy = credit_service.get_thread_billing_policy()
        raise PaymentRequiredError(
            f"Thread 免费额度已用尽。当前策略为前 {policy.free_tokens} tokens 免费，"
            "后续按 token 扣积分，请先补充积分。"
        )


def _build_thread_agent_runtime(
    request: ThreadTurnRequest,
    thread: Thread,
    *,
    actor_id: str,
    execution_id: str | None = None,
    workspace_service: WorkspaceService | None = None,
    index_service: Any | None = None,
    artifact_service: ArtifactService | None = None,
    reference_service: Any | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
) -> _ThreadAgentRuntime:
    from src.agents.chat_agent.agent import build_pipeline

    workspace_id = _resolve_workspace_id(request, thread)
    effective_skill = thread.skill
    effective_model = route_chat_model(
        requested_model=request.model,
        thread_model=thread.model,
        require_tools=True,
    )
    config = build_thread_runtime_config(
        request=request,
        thread=thread,
        actor_id=actor_id,
        workspace_id=workspace_id,
        effective_skill=effective_skill,
        effective_model=effective_model,
        execution_id=execution_id,
    )
    initial_state = build_thread_initial_state(
        thread,
        actor_id=actor_id,
        workspace_id=workspace_id,
        effective_skill=effective_skill,
        attachments=request.attachments,
        conversation_messages=conversation_messages,
    )
    middlewares = build_pipeline(
        config,
        workspace_service=workspace_service,
        index_service=index_service,
        artifact_service=artifact_service,
        reference_service=reference_service,
        memory_capture_enabled=False,
    )
    return _ThreadAgentRuntime(
        workspace_id=workspace_id,
        effective_skill=effective_skill,
        effective_model=effective_model,
        config=config,
        initial_state=initial_state,
        middlewares=middlewares,
    )


async def generate_thread_response(
    request: ThreadTurnRequest,
    thread: Thread,
    *,
    actor_id: str,
    execution_id: str | None = None,
    workspace_service: WorkspaceService | None = None,
    index_service: Any | None = None,
    artifact_service: ArtifactService | None = None,
    reference_service: Any | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    budget_checked: bool = False,
) -> GeneratedThreadReply:
    """Generate a thread response through the unified lead-agent pipeline."""
    from src.agents.chat_agent.agent import make_chat_agent

    # Handler.prepare_turn performs the production pre-persist budget gate.
    # Keep this fallback for direct unit-level calls into generate_thread_response.
    if not budget_checked:
        await ensure_thread_turn_budget(actor_id)

    runtime = _build_thread_agent_runtime(
        request,
        thread,
        actor_id=actor_id,
        workspace_service=workspace_service,
        index_service=index_service,
        artifact_service=artifact_service,
        reference_service=reference_service,
        conversation_messages=conversation_messages,
    )

    agent = cast(Any, make_chat_agent(runtime.config, middlewares=runtime.middlewares))
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
    reply = _attach_usage_metadata(
        reply,
        extract_usage_from_agent_result(result),
        model_name=runtime.effective_model,
        source="thread_agent",
    )
    return _normalize_reply_orchestration_metadata(
        reply,
        request_metadata=request.metadata,
        execution_id=execution_id,
    )


def stream_thread_response(
    request: ThreadTurnRequest,
    thread: Thread,
    *,
    actor_id: str,
    execution_id: str | None = None,
    workspace_service: WorkspaceService | None = None,
    index_service: Any | None = None,
    artifact_service: ArtifactService | None = None,
    reference_service: Any | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    budget_checked: bool = False,
) -> _ReplyStreamRun:
    """Stream a thread response while still returning the final structured reply."""
    from src.agents.chat_agent.agent import make_chat_agent

    reply_future: asyncio.Future[GeneratedThreadReply] = asyncio.get_running_loop().create_future()

    async def _iterator() -> AsyncIterator[ThreadStreamDelta]:
        accumulated_reasoning = ""
        emitted_any_delta = False
        try:
            if not budget_checked:
                await ensure_thread_turn_budget(actor_id)

            runtime = _build_thread_agent_runtime(
                request,
                thread,
                actor_id=actor_id,
                workspace_service=workspace_service,
                index_service=index_service,
                artifact_service=artifact_service,
                reference_service=reference_service,
                conversation_messages=conversation_messages,
            )
            agent = cast(
                Any,
                make_chat_agent(runtime.config, middlewares=runtime.middlewares),
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
                        yield ThreadStreamDelta(kind="content", text=reply.content)
                    if not reply_future.done():
                        reply_future.set_result(reply)
                    return
                reply = _attach_usage_metadata(
                    _reply_from_agent_result(result, thread_id=thread.id),
                    extract_usage_from_agent_result(result),
                    model_name=runtime.effective_model,
                    source="thread_agent",
                )
                reply = _normalize_reply_orchestration_metadata(
                    reply,
                    request_metadata=request.metadata,
                    execution_id=execution_id,
                )
                reasoning_text = _reply_reasoning_text(reply)
                if reasoning_text:
                    yield ThreadStreamDelta(kind="reasoning", text=reasoning_text)
                if reply.content:
                    yield ThreadStreamDelta(kind="content", text=reply.content)
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
                        if delta.kind in {"tool_invocation", "tool_result"}:
                            emitted_any_delta = True
                            yield delta
                            continue
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
                                emitted_any_delta = True
                                yield ThreadStreamDelta(
                                    kind="reasoning",
                                    text=normalized_text,
                                )
                            continue
                        if delta.text:
                            emitted_any_delta = True
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
                        yield ThreadStreamDelta(kind="content", text=reply.content)
                    if not reply_future.done():
                        reply_future.set_result(reply)
                    return

            reply = _attach_usage_metadata(
                _reply_from_agent_result(result, thread_id=thread.id),
                extract_usage_from_agent_result(result),
                model_name=runtime.effective_model,
                source="thread_agent",
            )
            reply = _normalize_reply_orchestration_metadata(
                reply,
                request_metadata=request.metadata,
                execution_id=execution_id,
            )
            if not emitted_any_delta:
                for block in reply.blocks:
                    if not isinstance(block, Mapping):
                        continue
                    kind = block.get("kind")
                    if kind in {"tool_invocation", "tool_result"}:
                        data = block.get("data")
                        if isinstance(data, Mapping):
                            yield ThreadStreamDelta(kind=kind, data=dict(data))
                reasoning_text = _reply_reasoning_text(reply)
                if reasoning_text:
                    yield ThreadStreamDelta(kind="reasoning", text=reasoning_text)
                if reply.content:
                    yield ThreadStreamDelta(kind="content", text=reply.content)
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
            raise exc from None
        except Exception as exc:
            if not reply_future.done():
                reply_future.set_exception(exc)
            raise

    return _ReplyStreamRun(_iterator(), reply_future)
