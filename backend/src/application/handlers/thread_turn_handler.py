"""Application-layer orchestration for thread turns."""

from __future__ import annotations

import ast
import asyncio
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
from uuid import uuid4

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
from src.agents.contracts.intake_spec import IntakeSpecV1
from src.config import get_model_config
from src.config.config_loader import get_app_config
from src.config.llm_config import LLMSettings
from src.models import model_supports_vision, route_chat_model
from src.models.router import InvalidRequestedModelError
from src.services import ThreadAccessError, ThreadService
from src.services.credit_service import CreditService
from src.services.thread_billing import (
    extract_usage_from_agent_result,
    normalize_token_usage,
    usage_to_metadata,
)
from src.services.thread_events import publish_thread_updated, set_thread_status
from src.tools.builtins.artifacts import (
    build_presented_artifact_items,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.dataservice_client.contracts.conversation import ConversationThreadPayload as Thread

_THREAD_VIRTUAL_ROOT = "/mnt/user-data/"
_THREAD_UPLOADS_VIRTUAL_ROOT = "/mnt/user-data/uploads/"
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
_INTAKE_GATED_FEATURE_IDS = {
    "software_copyright_application_pack",
    "math_modeling_paper_pack",
}
_INTAKE_WORKSPACE_BY_FEATURE_ID = {
    "software_copyright_application_pack": "software_copyright",
    "math_modeling_paper_pack": "math_modeling",
}
_INTAKE_FEATURE_BY_WORKSPACE_TYPE = {
    value: key for key, value in _INTAKE_WORKSPACE_BY_FEATURE_ID.items()
}
_INTAKE_TRIGGER_TERMS = (
    "spec",
    "澄清",
    "软著申请材料包",
    "软著申报",
    "数学建模论文包",
    "数学建模",
    "开始写",
    "开始做",
    "按这个",
    "执行",
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


def _extract_intake_feature_id_from_metadata(
    metadata: Mapping[str, Any] | None,
) -> str | None:
    if not isinstance(metadata, Mapping):
        return None
    for bucket_name, key_name in (
        ("workbench_launch", "capability_id"),
        ("orchestration", "feature_id"),
        ("entry_seed", "feature_id"),
    ):
        bucket = metadata.get(bucket_name)
        if not isinstance(bucket, Mapping):
            continue
        feature_id = str(bucket.get(key_name) or "").strip()
        if feature_id in _INTAKE_GATED_FEATURE_IDS:
            return feature_id
    return None


def _workspace_type_for_intake(
    *,
    thread: Any,
    feature_id: str | None,
) -> str | None:
    if feature_id in _INTAKE_WORKSPACE_BY_FEATURE_ID:
        return _INTAKE_WORKSPACE_BY_FEATURE_ID[feature_id]
    workspace_type = str(getattr(thread, "workspace_type", "") or "").strip()
    if workspace_type in _INTAKE_FEATURE_BY_WORKSPACE_TYPE:
        return workspace_type
    return None


def _recent_user_text(
    *,
    request: ThreadTurnRequest,
    conversation_messages: list[dict[str, Any]] | None,
    limit: int = 8,
) -> str:
    texts: list[str] = []
    for message in list(conversation_messages or [])[-limit:]:
        if not isinstance(message, Mapping):
            continue
        if str(message.get("role") or "").strip() != "user":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            texts.append(content)
    if request.message.strip() and request.message.strip() not in texts:
        texts.append(request.message.strip())
    return "\n".join(texts[-limit:]).strip()


def _looks_like_intake_turn(
    *,
    request: ThreadTurnRequest,
    thread: Any,
    conversation_messages: list[dict[str, Any]] | None,
) -> tuple[str, str] | None:
    feature_id = _extract_intake_feature_id_from_metadata(request.metadata)
    workspace_type = _workspace_type_for_intake(thread=thread, feature_id=feature_id)
    if workspace_type is None:
        return None
    feature_id = feature_id or _INTAKE_FEATURE_BY_WORKSPACE_TYPE.get(workspace_type)
    if not feature_id:
        return None

    if _extract_intake_feature_id_from_metadata(request.metadata):
        return workspace_type, feature_id

    text = _recent_user_text(request=request, conversation_messages=conversation_messages)
    normalized = text.lower()
    if any(term.lower() in normalized for term in _INTAKE_TRIGGER_TERMS):
        return workspace_type, feature_id
    return None


def _first_regex_group(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    value = str(match.group(1) or "").strip()
    return value.strip(" ：:，,。.;；") or None


def _last_regex_group(pattern: str, text: str) -> str | None:
    matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
    if not matches:
        return None
    value = str(matches[-1].group(1) or "").strip()
    return value.strip(" ：:，,。.;；") or None


def _split_feature_points(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = re.sub(r"[。.\n].*$", "", value).strip()
    parts = re.split(r"[、,，;；]|以及|和", normalized)
    return [part.strip() for part in parts if part.strip()][:12]


def _software_intake_params(text: str) -> tuple[dict[str, Any], list[str], list[str]]:
    quoted_name = _last_regex_group(r"《([^》]+)》", text)
    software_name = (
        _last_regex_group(r"软件(?:名称|全称)?\s*[:：]\s*([^。\n；;]+)", text)
        or quoted_name
    )
    software_name = software_name.strip() if software_name else ""

    lowered = text.lower()
    app_type = "web" if "web" in lowered else "app" if "app" in lowered else ""
    backend_language = ""
    for language in ("java", "python", "go", "node", "typescript", "php", "c#"):
        if language in lowered:
            backend_language = "Node.js" if language == "node" else language.upper() if language == "go" else language.title()
            if language == "java":
                backend_language = "Java"
            if language == "python":
                backend_language = "Python"
            break

    target_users = _last_regex_group(r"面向([^。；;\n]+)", text) or ""
    feature_points = _split_feature_points(
        _last_regex_group(r"(?:核心功能(?:包括|有)?|功能(?:包括|有)?)\s*[：:,，]?\s*([^。\n]+)", text)
    )

    missing_fields: list[str] = []
    if not software_name:
        missing_fields.append("software_name")
    if not app_type:
        missing_fields.append("software_type")
    if not feature_points:
        missing_fields.append("core_features")

    assumptions: list[str] = []
    if not backend_language:
        backend_language = "Java"
        assumptions.append("未明确后端语言时，软著材料按 Java 后端 mock 代码组织。")
    if not app_type:
        app_type = "web"
        assumptions.append("未明确 Web/App 时，先按 Web 系统和静态前端截图组织界面证据。")

    params = {
        "software_name": software_name,
        "software_type": app_type,
        "backend_language": backend_language,
        "target_users": target_users,
        "core_features": feature_points,
        "evidence_strategy": {
            "backend_code": "mock_backend_code",
            "ui_evidence": "static_frontend_screenshot",
        },
        "visual_strategy": {
            "ui_screenshots": "static_frontend_screenshot",
            "architecture_diagrams": "engineering_diagram",
        },
    }
    return params, missing_fields, assumptions


def _software_intake_markdown(
    *,
    title: str,
    params: Mapping[str, Any],
    missing_fields: list[str],
    assumptions: list[str],
) -> str:
    features = params.get("core_features")
    feature_lines = "\n".join(
        f"- {item}" for item in features if isinstance(item, str) and item.strip()
    ) or "- 待补充核心功能点"
    missing = "\n".join(f"- {item}" for item in missing_fields) or "- 无"
    assumption_lines = "\n".join(f"- {item}" for item in assumptions) or "- 无"
    return "\n".join(
        [
            f"# {title}",
            "",
            "## 目标",
            f"- 生成软件著作权申报材料包，软件名称：{params.get('software_name') or '待补充'}。",
            "- 交付申请表填报素材、软件说明、功能模块说明、用户手册/说明书摘要、材料清单和证据整理建议。",
            "",
            "## 技术与证据口径",
            f"- 系统类型：{params.get('software_type') or '待补充'}",
            f"- 后端代码：{params.get('backend_language') or '待补充'} mock 后端代码",
            "- 应用页面证据：静态前端页面构建与截图，不使用 AI 生成 UI 图作为申报证据。",
            "",
            "## 核心功能",
            feature_lines,
            "",
            "## 缺失信息",
            missing,
            "",
            "## 暂定假设",
            assumption_lines,
        ]
    )


def _math_intake_params(text: str, attachments: tuple[ThreadTurnAttachment, ...]) -> tuple[dict[str, Any], list[str], list[str]]:
    problem_statement = (
        _first_regex_group(r"(?:赛题|题目|题面|problem)\s*[:：]\s*([\s\S]+)", text)
        or text.strip()
    )
    if len(problem_statement) < 30 and not attachments:
        problem_statement = ""

    missing_fields: list[str] = []
    if not problem_statement:
        missing_fields.append("problem_statement")

    assumptions = [
        "数模编程统一使用 Python，不再询问编程语言。",
        "论文格式按高教社杯全国大学生数学建模竞赛常见 LaTeX 规范组织。",
    ]
    params = {
        "problem_statement": problem_statement,
        "programming_language": "python",
        "competition_standard": "高教社杯全国大学生数学建模竞赛",
        "has_data_attachments": bool(attachments),
        "deliverables": [
            "建模思路",
            "Python 求解脚本",
            "论文图表",
            "LaTeX 论文初稿",
            "格式检查清单",
        ],
        "figure_style": {
            "palette": "academic_blue_orange",
            "output_format": "pdf_png",
        },
    }
    return params, missing_fields, assumptions


def _math_intake_markdown(
    *,
    title: str,
    params: Mapping[str, Any],
    missing_fields: list[str],
    assumptions: list[str],
) -> str:
    missing = "\n".join(f"- {item}" for item in missing_fields) or "- 无"
    assumption_lines = "\n".join(f"- {item}" for item in assumptions) or "- 无"
    problem = str(params.get("problem_statement") or "待补充赛题题面").strip()
    return "\n".join(
        [
            f"# {title}",
            "",
            "## 目标",
            "- 输入赛题后生成建模方案、Python 求解脚本、图表、LaTeX 论文初稿和格式检查包。",
            "",
            "## 赛题摘要",
            problem[:1800],
            "",
            "## 执行约束",
            "- 编程语言：Python",
            "- 格式规范：高教社杯全国大学生数学建模竞赛常见论文规范",
            "- 图表风格：学术蓝橙配色，输出 PDF/PNG 级别图件",
            "",
            "## 缺失信息",
            missing,
            "",
            "## 暂定假设",
            assumption_lines,
        ]
    )


def _build_intake_spec_fallback(
    *,
    request: ThreadTurnRequest,
    thread: Any,
    conversation_messages: list[dict[str, Any]] | None,
) -> IntakeSpecV1 | None:
    intake = _looks_like_intake_turn(
        request=request,
        thread=thread,
        conversation_messages=conversation_messages,
    )
    if intake is None:
        return None
    workspace_type, feature_id = intake
    text = _recent_user_text(request=request, conversation_messages=conversation_messages)
    workspace_id = (
        str(getattr(thread, "workspace_id", "") or "").strip()
        or str(request.workspace_id or "").strip()
    )
    if not workspace_id:
        return None

    if workspace_type == "software_copyright":
        params, missing_fields, assumptions = _software_intake_params(text)
        software_name = str(params.get("software_name") or "").strip()
        title = f"{software_name or '软件著作权'}申报材料包 Spec"
        markdown = _software_intake_markdown(
            title=title,
            params=params,
            missing_fields=missing_fields,
            assumptions=assumptions,
        )
    else:
        params, missing_fields, assumptions = _math_intake_params(text, request.attachments)
        title = "数学建模论文包执行 Spec"
        markdown = _math_intake_markdown(
            title=title,
            params=params,
            missing_fields=missing_fields,
            assumptions=assumptions,
        )

    status = "ready" if not missing_fields else "draft"
    try:
        return IntakeSpecV1(
            spec_id=f"intake-{uuid4().hex}",
            revision=1,
            workspace_id=workspace_id,
            workspace_type=cast(Any, workspace_type),
            capability_id=cast(Any, feature_id),
            title=title,
            status=cast(Any, status),
            markdown=markdown,
            params=params,
            missing_fields=missing_fields,
            assumptions=assumptions,
        )
    except Exception:
        logger.debug("Failed to build deterministic intake spec fallback", exc_info=True)
        return None


def _intake_spec_tool_result_block(spec: IntakeSpecV1) -> dict[str, Any]:
    return {
        "kind": "tool_result",
        "tool": "draft_intake_spec",
        "status": spec.status,
        "tool_call_id": f"intake_fallback_{uuid4().hex}",
        "output": {
            "status": spec.status,
            "intake_spec": spec.model_dump(mode="json"),
            "fallback": True,
        },
    }


def _reply_has_intake_spec(reply: GeneratedThreadReply) -> bool:
    for block in reply.blocks if isinstance(reply.blocks, list) else []:
        if not isinstance(block, Mapping):
            continue
        payload = block.get("output")
        payload = payload if isinstance(payload, Mapping) else block
        intake_spec = payload.get("intake_spec") if isinstance(payload, Mapping) else None
        if isinstance(intake_spec, Mapping) and intake_spec.get("schema_version") == "wenjin.intake_spec.v1":
            return True
    return False


def _maybe_attach_intake_spec_fallback(
    reply: GeneratedThreadReply,
    *,
    request: ThreadTurnRequest,
    thread: Any,
    conversation_messages: list[dict[str, Any]] | None,
) -> GeneratedThreadReply:
    if _reply_has_intake_spec(reply):
        return reply
    spec = _build_intake_spec_fallback(
        request=request,
        thread=thread,
        conversation_messages=conversation_messages,
    )
    if spec is None:
        return reply

    reply.blocks = [*list(reply.blocks or []), _intake_spec_tool_result_block(spec)]
    reply.metadata = dict(reply.metadata or {})
    reply.metadata["intake_spec_fallback"] = {
        "spec_id": spec.spec_id,
        "status": spec.status,
    }
    if not reply.content.strip():
        reply.content = (
            f"已整理好「{spec.title}」。请先查看澄清 Spec，确认后再开始执行。"
        )
    return reply


def _build_intake_spec_fallback_reply(
    *,
    request: ThreadTurnRequest,
    thread: Any,
    conversation_messages: list[dict[str, Any]] | None,
) -> GeneratedThreadReply | None:
    spec = _build_intake_spec_fallback(
        request=request,
        thread=thread,
        conversation_messages=conversation_messages,
    )
    if spec is None:
        return None
    return GeneratedThreadReply(
        content=f"已整理好「{spec.title}」。请先查看澄清 Spec，确认后再开始执行。",
        blocks=[_intake_spec_tool_result_block(spec)],
        metadata={
            "intake_spec_fallback": {
                "spec_id": spec.spec_id,
                "status": spec.status,
            }
        },
    )


def _stringify_persisted_message_content(message: Mapping[str, Any]) -> str:
    role = str(message.get("role") or "").strip()
    content = str(message.get("content") or "").strip()

    if role not in {"user", "assistant"}:
        return content

    additions: list[str] = []
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
    user_message_id: str | None = None,
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
    if user_message_id:
        configurable["user_message_id"] = user_message_id
        configurable["launch_idempotency_key"] = (
            f"launch_feature:{thread.id}:{user_message_id}"
        )
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
        if isinstance(nested_content, str) and nested_content.strip():
            return nested_content.strip()
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
    block_type = str(block.get("type") or block.get("kind") or "").lower()
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


def _build_thinking_block(reasoning_text: str) -> dict[str, Any]:
    return {"kind": "thinking", "text": reasoning_text}


def _is_thinking_block(block: Mapping[str, Any]) -> bool:
    block_kind = str(block.get("kind") or block.get("type") or "").strip().lower()
    return block_kind in {"thinking", "reasoning", "reasoning_content"}


def _reply_reasoning_text(reply: GeneratedThreadReply) -> str:
    blocks = reply.blocks if isinstance(reply.blocks, list) else []
    for block in blocks:
        if not isinstance(block, Mapping) or not _is_thinking_block(block):
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        content = block.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
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


_CANONICAL_RESPONSE_BLOCK_KINDS = {
    "text",
    "thinking",
    "status_line",
    "question_card",
    "result_card",
    "tool_invocation",
    "tool_result",
}
_RESPONSE_BLOCK_KIND_ALIASES = {
    "reasoning": "thinking",
    "reasoning_content": "thinking",
    "thought": "thinking",
    "warning": "status_line",
    "tool": "tool_invocation",
    "tool_call": "tool_invocation",
    "tool_use": "tool_invocation",
}


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _is_safe_visible_block_text(value: str) -> bool:
    lowered = value.lower()
    unsafe_markers = (
        "/mnt/user-data",
        "/workspace/",
        "/private/",
        "output_ref",
        "storage_path",
    )
    return not any(marker in lowered for marker in unsafe_markers)


def _safe_visible_string(value: Any) -> str | None:
    text = _string_value(value)
    if text and _is_safe_visible_block_text(text):
        return text
    return None


def _block_data_payload(block: Mapping[str, Any]) -> Mapping[str, Any]:
    data = block.get("data")
    if isinstance(data, Mapping):
        return data
    return {}


def _visible_block_text(block: Mapping[str, Any]) -> str:
    data = _block_data_payload(block)
    content = block.get("content")
    content_payload = content if isinstance(content, Mapping) else {}
    title = (
        _safe_visible_string(block.get("title"))
        or _safe_visible_string(block.get("label"))
        or _safe_visible_string(block.get("name"))
    )
    detail = (
        _safe_visible_string(block.get("detail"))
        or _safe_visible_string(block.get("message"))
        or _safe_visible_string(block.get("summary"))
        or _safe_visible_string(data.get("detail"))
        or _safe_visible_string(data.get("message"))
        or _safe_visible_string(data.get("summary"))
        or _safe_visible_string(data.get("text"))
        or _safe_visible_string(data.get("content"))
        or _safe_visible_string(content_payload.get("detail"))
        or _safe_visible_string(content_payload.get("message"))
        or _safe_visible_string(content_payload.get("summary"))
        or _safe_visible_string(content_payload.get("text"))
        or _safe_visible_string(content_payload.get("content"))
        or _safe_visible_string(block.get("content"))
        or _safe_visible_string(block.get("text"))
    )
    if title and detail and title != detail:
        return f"{title}：{detail}"
    return title or detail or ""


def _fallback_block_text(block: Mapping[str, Any]) -> str:
    visible = _visible_block_text(block)
    if visible:
        return visible
    return "Unsupported message block"


def _response_block_raw_kind(block: Mapping[str, Any]) -> str:
    return str(block.get("kind") or block.get("type") or "").strip().lower()


def _extract_tool_name_from_block(payload: Mapping[str, Any]) -> str | None:
    for key in ("tool", "tool_name", "name", "function_name"):
        value = _string_value(payload.get(key))
        if value:
            return value
    function = payload.get("function")
    if isinstance(function, Mapping):
        return _string_value(function.get("name"))
    return None


def _extract_tool_input_from_block(payload: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("input", "args", "arguments", "parameters"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _extract_tool_call_id_from_block(payload: Mapping[str, Any]) -> str | None:
    for key in ("tool_call_id", "invocation_id", "call_id", "id"):
        value = _string_value(payload.get(key))
        if value:
            return value
    return None


def _extract_tool_output_from_block(
    raw: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    for payload in (raw, source):
        for key in ("output", "result"):
            value = payload.get(key)
            if isinstance(value, Mapping):
                return dict(value)
            if value is not None:
                return {"value": value}
    data = raw.get("data")
    if isinstance(data, Mapping):
        return dict(data)
    omitted = {"kind", "type", "output", "result", "data"}
    return {
        str(key): value
        for key, value in source.items()
        if isinstance(key, str) and key not in omitted
    }


def _normalize_tool_invocation_response_block(
    block: Mapping[str, Any],
) -> dict[str, Any]:
    source = _block_data_payload(block) or block
    normalized: dict[str, Any] = {
        "kind": "tool_invocation",
        "tool": (
            _extract_tool_name_from_block(source)
            or _extract_tool_name_from_block(block)
            or "unknown"
        ),
        "input": _extract_tool_input_from_block(source),
    }
    tool_call_id = (
        _extract_tool_call_id_from_block(source)
        or _extract_tool_call_id_from_block(block)
    )
    if tool_call_id:
        normalized["tool_call_id"] = tool_call_id
    return normalized


def _normalize_tool_result_response_block(
    block: Mapping[str, Any],
) -> dict[str, Any]:
    source = _block_data_payload(block) or block
    output = _extract_tool_output_from_block(block, source)
    normalized: dict[str, Any] = {
        "kind": "tool_result",
        "tool": (
            _extract_tool_name_from_block(source)
            or _extract_tool_name_from_block(block)
            or "unknown"
        ),
        "output": output,
    }
    status = source.get("status", block.get("status"))
    if status is not None:
        normalized["status"] = str(status)
    tool_call_id = (
        _extract_tool_call_id_from_block(source)
        or _extract_tool_call_id_from_block(block)
    )
    if tool_call_id:
        normalized["tool_call_id"] = tool_call_id
    for key in ("execution_id", "feature_id"):
        value = source.get(key, block.get(key, output.get(key)))
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
    return normalized


def _normalize_status_line_response_block(
    block: Mapping[str, Any],
    *,
    raw_kind: str,
) -> dict[str, Any]:
    tone = block.get("tone")
    normalized_tone = (
        tone
        if tone in {"info", "warn", "error"}
        else "warn"
        if raw_kind == "warning"
        else "info"
    )
    normalized: dict[str, Any] = {
        "kind": "status_line",
        "label": _string_value(block.get("label"))
        or _visible_block_text(block)
        or "Status update",
        "run_id": _string_value(block.get("run_id"))
        or ("warning-status" if raw_kind == "warning" else "status-line"),
        "tone": normalized_tone,
    }
    phase_index = block.get("phase_index")
    if isinstance(phase_index, int):
        normalized["phase_index"] = phase_index
    return normalized


def _normalize_response_block(block: Mapping[str, Any]) -> dict[str, Any] | None:
    raw_kind = _response_block_raw_kind(block)
    kind = _RESPONSE_BLOCK_KIND_ALIASES.get(raw_kind, raw_kind)
    if kind == "artifacts":
        return None

    if kind == "thinking":
        return {
            "kind": "thinking",
            "text": _extract_reasoning_text_from_payload(block)
            or _fallback_block_text(block),
        }

    if kind == "text":
        content = block.get("content")
        if isinstance(content, str):
            return {"kind": "text", "content": content}
        text = block.get("text")
        if isinstance(text, str):
            return {"kind": "text", "content": text}
        return {"kind": "text", "content": _fallback_block_text(block)}

    if kind == "status_line":
        return _normalize_status_line_response_block(block, raw_kind=raw_kind)

    if kind == "tool_invocation":
        return _normalize_tool_invocation_response_block(block)

    if kind == "tool_result":
        return _normalize_tool_result_response_block(block)

    if kind in _CANONICAL_RESPONSE_BLOCK_KINDS:
        normalized = dict(block)
        normalized["kind"] = kind
        normalized.pop("type", None)
        return normalized

    return {"kind": "text", "content": _fallback_block_text(block)}


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
                "kind": "status_line",
                "label": "能力未启动：缺少真实 launch_feature 工具结果",
                "run_id": "unbacked_launch_receipt",
                "tone": "warn",
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

    response_blocks = [
        normalized
        for block in (result.get("response_blocks") or [])
        if isinstance(block, Mapping)
        if (normalized := _normalize_response_block(block)) is not None
    ]
    launch_blocks = _extract_launch_feature_blocks(messages)
    if not launch_blocks and _looks_like_unbacked_launch_receipt(content):
        return _build_unbacked_launch_receipt_guard_reply()

    blocks: list[dict[str, Any]] = [*launch_blocks]
    raw_response_metadata = result.get("response_metadata")
    metadata = (
        dict(raw_response_metadata)
        if isinstance(raw_response_metadata, dict)
        else {}
    )
    if reasoning_text:
        metadata["reasoning"] = {"text": reasoning_text}
        if not any(
            isinstance(block, dict) and _is_thinking_block(block)
            for block in [*blocks, *response_blocks]
        ):
            blocks.append(_build_thinking_block(reasoning_text))

    blocks.extend(response_blocks)

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
        invocation = {
            "tool": name,
            "input": dict(args) if isinstance(args, Mapping) else {},
        }
        tool_call_id = call.get("id") or call.get("tool_call_id") or call.get("call_id")
        if isinstance(tool_call_id, str) and tool_call_id.strip():
            invocation["tool_call_id"] = tool_call_id.strip()
        invocations.append(invocation)
    return invocations


def _extract_launch_feature_result(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, ToolMessage):
        return None
    payload = _coerce_tool_result_payload(message.content)
    if not payload:
        return None
    if not payload.get("status") or not payload.get("feature_id"):
        return None
    result: dict[str, Any] = {
        "tool": "launch_feature",
        "output": payload,
    }
    status = payload.get("status")
    if status is not None:
        result["status"] = str(status)
    execution_id = payload.get("execution_id")
    if isinstance(execution_id, str) and execution_id.strip():
        result["execution_id"] = execution_id.strip()
    feature_id = payload.get("feature_id")
    if isinstance(feature_id, str) and feature_id.strip():
        result["feature_id"] = feature_id.strip()
    tool_call_id = getattr(message, "tool_call_id", None)
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        result["tool_call_id"] = tool_call_id.strip()
    return result


def _extract_launch_feature_blocks(messages: list[Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    seen_results: set[tuple[str, str]] = set()

    for message in messages:
        for invocation in _extract_launch_feature_invocations(message):
            blocks.append({"kind": "tool_invocation", **invocation})

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
        blocks.append({"kind": "tool_result", **result})

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

        user_message = await self.thread_service.add_message(
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
        user_message_id = (
            str(user_message.get("id") or "").strip()
            if isinstance(user_message, Mapping)
            else ""
        )
        return PreparedThreadTurn(
            request=request,
            thread=thread,
            user_message_id=user_message_id or None,
        )

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
                    user_message_id=prepared.user_message_id,
                    conversation_messages=conversation_messages,
                )
                async for delta in reply_stream:
                    if delta.text or delta.data is not None:
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
        user_message_id: str | None = None,
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

        billing_context = {
            "source": (
                usage_metadata.get("source", "thread")
                if usage_metadata is not None
                else "thread"
            )
        }
        if user_message_id:
            billing_context["user_message_id"] = user_message_id
            billing_context["idempotency_key"] = f"thread_token_billing:{user_message_id}"

        credit_service = CreditService()
        billing = await credit_service.consume_for_thread_usage(
            user_id=actor_id,
            token_usage=normalized_usage,
            model_name=usage_metadata.get("model_name") if usage_metadata else None,
            workspace_id=thread.workspace_id,
            thread_id=thread.id,
            metadata=billing_context,
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
                user_message_id=prepared.user_message_id,
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

        credit_service = CreditService()
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
            user_message_id=prepared.user_message_id,
        )

    async def _generate_thread_response(
        self,
        request: ThreadTurnRequest,
        thread: Thread,
        *,
        actor_id: str,
        execution_id: str | None = None,
        user_message_id: str | None = None,
    ) -> GeneratedThreadReply:
        await self._maybe_compact_thread_history(thread)
        conversation_messages = await self.thread_service.list_thread_messages(thread)
        return await generate_thread_response(
            request,
            thread,
            actor_id=actor_id,
            execution_id=execution_id,
            user_message_id=user_message_id,
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
        user_message_id: str | None = None,
        conversation_messages: list[dict[str, Any]] | None = None,
    ) -> _ReplyStreamRun:
        return stream_thread_response(
            request,
            thread,
            actor_id=actor_id,
            execution_id=execution_id,
            user_message_id=user_message_id,
            workspace_service=self.workspace_service,
            index_service=self.index_service,
            artifact_service=self.artifact_service,
            reference_service=self.reference_service,
            conversation_messages=conversation_messages,
            budget_checked=True,
        )


async def ensure_thread_turn_budget(actor_id: str) -> None:
    """Reject pure thread turns once free quota is exhausted and credits are empty."""
    credit_service = CreditService()
    allowed = await credit_service.can_start_thread_turn(actor_id)
    if allowed:
        return
    raise PaymentRequiredError(
        "主线对话积分额度不足，请先补充积分后继续。"
    )


def _build_thread_agent_runtime(
    request: ThreadTurnRequest,
    thread: Thread,
    *,
    actor_id: str,
    execution_id: str | None = None,
    user_message_id: str | None = None,
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
        user_message_id=user_message_id,
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
    user_message_id: str | None = None,
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
        execution_id=execution_id,
        user_message_id=user_message_id,
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
    user_message_id: str | None = None,
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
                execution_id=execution_id,
                user_message_id=user_message_id,
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
                reply = _maybe_attach_intake_spec_fallback(
                    reply,
                    request=request,
                    thread=thread,
                    conversation_messages=conversation_messages,
                )
                reasoning_text = _reply_reasoning_text(reply)
                if reasoning_text:
                    yield ThreadStreamDelta(kind="reasoning", text=reasoning_text)
                if reply.content:
                    yield ThreadStreamDelta(kind="content", text=reply.content)
                for block in reply.blocks:
                    if not isinstance(block, Mapping) or block.get("kind") != "tool_result":
                        continue
                    data = {
                        str(key): value
                        for key, value in block.items()
                        if key != "kind"
                    }
                    yield ThreadStreamDelta(kind="tool_result", data=data)
                if not reply_future.done():
                    reply_future.set_result(reply)
                return

            stream_run = agent.astream_with_result(
                runtime.initial_state,
                config=runtime.config,
                stream_mode=["messages", "values"],
            )
            emitted_tool_result = False
            async with asyncio.timeout(LLMSettings.AGENT_TIMEOUT):
                async for mode, payload in stream_run:
                    if mode != "messages":
                        continue
                    chunk, metadata = payload
                    for delta in _stream_deltas_from_chunk(chunk, metadata):
                        if delta.kind in {"tool_invocation", "tool_result"}:
                            emitted_any_delta = True
                            if delta.kind == "tool_result":
                                emitted_tool_result = True
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
                    reply = _build_intake_spec_fallback_reply(
                        request=request,
                        thread=thread,
                        conversation_messages=conversation_messages,
                    ) or _build_recursion_guard_reply(request=request)
                    if reply.content:
                        yield ThreadStreamDelta(kind="content", text=reply.content)
                    for block in reply.blocks:
                        if not isinstance(block, Mapping) or block.get("kind") != "tool_result":
                            continue
                        data = {
                            str(key): value
                            for key, value in block.items()
                            if key != "kind"
                        }
                        yield ThreadStreamDelta(kind="tool_result", data=data)
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
            reply = _maybe_attach_intake_spec_fallback(
                reply,
                request=request,
                thread=thread,
                conversation_messages=conversation_messages,
            )
            emitted_reply_tool_result = False
            if not emitted_tool_result:
                for block in reply.blocks:
                    if not isinstance(block, Mapping) or block.get("kind") != "tool_result":
                        continue
                    data = {
                        str(key): value
                        for key, value in block.items()
                        if key != "kind"
                    }
                    yield ThreadStreamDelta(kind="tool_result", data=data)
                    emitted_tool_result = True
                    emitted_reply_tool_result = True
            if not emitted_any_delta:
                for block in reply.blocks:
                    if not isinstance(block, Mapping):
                        continue
                    kind = block.get("kind")
                    if kind in {"tool_invocation", "tool_result"}:
                        if kind == "tool_result" and emitted_reply_tool_result:
                            continue
                        data = {
                            str(key): value
                            for key, value in block.items()
                            if key != "kind"
                        }
                        yield ThreadStreamDelta(kind=kind, data=data)
                reasoning_text = _reply_reasoning_text(reply)
                if reasoning_text:
                    yield ThreadStreamDelta(kind="reasoning", text=reasoning_text)
                if reply.content:
                    yield ThreadStreamDelta(kind="content", text=reply.content)
            if not reply_future.done():
                reply_future.set_result(reply)
        except GraphRecursionError:
            logger.warning(
                "Agent recursion guard triggered for thread %s (streaming)",
                thread.id,
            )
            reply = _build_intake_spec_fallback_reply(
                request=request,
                thread=thread,
                conversation_messages=conversation_messages,
            ) or _build_recursion_guard_reply(request=request)
            if reply.content:
                yield ThreadStreamDelta(kind="content", text=reply.content)
            for block in reply.blocks:
                if not isinstance(block, Mapping) or block.get("kind") != "tool_result":
                    continue
                data = {
                    str(key): value
                    for key, value in block.items()
                    if key != "kind"
                }
                yield ThreadStreamDelta(kind="tool_result", data=data)
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
