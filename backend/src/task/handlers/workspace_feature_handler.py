"""Unified workspace feature execution handler.

All workspace types now route through FeatureLeaderRuntime.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from src.services.token_usage_collector import (
    bind_token_usage_collector,
    get_collected_token_usage,
    reset_token_usage_collector,
)
from src.task.progress import (
    ProgressTracker,
    bind_progress_tracker,
    bind_runtime_state,
    reset_progress_tracker,
    reset_runtime_state,
)
from src.task.runtime_blocks import (
    advance_runtime_phase,
    append_runtime_activity,
    runtime_progress_for_phase,
)
from src.task.workspace_feature_artifacts import (
    persist_langgraph_artifacts as _persist_langgraph_artifacts,
)
from src.task.workspace_feature_runtime import (
    build_feature_runtime,
    enrich_runtime_with_result,
    resolve_runtime_next_phase,
)
from src.workspace_features import get_workspace_feature
from src.workspace_features.quality import evaluate_feature_output_quality

logger = logging.getLogger(__name__)

_THESIS_WRITING_LANGGRAPH_ACTIONS = {
    "generate_outline",
    "write_chapter",
    "write_all",
    "review_section",
    "revise_section",
    "review_and_revise",
}
_FEATURE_MEMORY_CONTEXT_KEYS = (
    "__thread_context_focus",
    "__leader_workflow_highlights",
    "topic",
    "query",
    "keywords",
    "goal",
    "task",
    "question",
    "requirements",
    "objective",
    "paper_title",
    "innovation_description",
    "__thread_context_digest",
)
_FEATURE_MEMORY_RESULT_KEYS = (
    "summary",
    "result_summary",
    "conclusion",
    "message",
)
_FEATURE_MEMORY_LINE_MAX_CHARS = 1200
_FEATURE_MEMORY_TEXT_MAX_CHARS = 3600


def _read_params(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params")
    return params if isinstance(params, dict) else {}


def _normalize_thesis_writing_action(
    raw_action: Any,
    *,
    default_action: str = "write_all",
) -> str:
    normalized = str(raw_action or "").strip().lower()
    return normalized or default_action


def _with_normalized_thesis_writing_payload(
    payload: dict[str, Any],
    *,
    default_action: str = "write_all",
) -> dict[str, Any]:
    params = _read_params(payload)
    normalized_action = _normalize_thesis_writing_action(
        params.get("action"),
        default_action=default_action,
    )
    normalized_params = dict(params)
    normalized_params["action"] = normalized_action

    normalized_payload = dict(payload)
    normalized_payload["params"] = normalized_params
    return normalized_payload


def _normalize_feature_memory_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _truncate_feature_memory_text(text: str, max_chars: int) -> str:
    normalized = _normalize_feature_memory_text(text)
    if len(normalized) <= max_chars:
        return normalized
    truncated = normalized[: max(0, max_chars - 1)].rstrip()
    return f"{truncated}…"


def _collect_feature_param_snippet(value: Any) -> str:
    if isinstance(value, str):
        return _normalize_feature_memory_text(value)
    if isinstance(value, list):
        items = [
            _normalize_feature_memory_text(item)
            for item in value
            if _normalize_feature_memory_text(item)
        ]
        return "；".join(items[:8]).strip()
    return ""


def _is_generic_feature_completion_message(message: str) -> bool:
    normalized = _normalize_feature_memory_text(message)
    return bool(normalized) and "已通过 LangGraph 增强完成" in normalized


def _build_feature_memory_conversation(
    workspace_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> str:
    """Build a concise pseudo-conversation for feature memory extraction."""
    params = _read_params(payload)
    user_parts: list[str] = []
    for key in _FEATURE_MEMORY_CONTEXT_KEYS:
        snippet = _collect_feature_param_snippet(params.get(key))
        if not snippet:
            continue
        if key == "__thread_context_digest":
            snippet = _truncate_feature_memory_text(snippet, 1600)
        user_parts.append(snippet)
    user_parts = list(dict.fromkeys(user_parts))

    assistant_parts: list[str] = []
    wrapped_message = _normalize_feature_memory_text(result.get("message"))
    if wrapped_message and not _is_generic_feature_completion_message(wrapped_message):
        assistant_parts.append(wrapped_message)

    data = result.get("data")
    if isinstance(data, dict):
        for key in _FEATURE_MEMORY_RESULT_KEYS:
            snippet = _normalize_feature_memory_text(data.get(key))
            if snippet:
                assistant_parts.append(snippet)

        sections = data.get("sections")
        if isinstance(sections, list):
            section_titles = [
                _normalize_feature_memory_text(item.get("title"))
                for item in sections
                if isinstance(item, dict) and _normalize_feature_memory_text(item.get("title"))
            ]
            if section_titles:
                assistant_parts.append("输出章节: " + " / ".join(section_titles[:4]))

        recommended_actions = data.get("recommended_actions") or data.get("next_actions")
        if isinstance(recommended_actions, list):
            action_labels: list[str] = []
            for action in recommended_actions[:4]:
                if not isinstance(action, dict):
                    continue
                label = _normalize_feature_memory_text(
                    action.get("action")
                    or action.get("label")
                    or action.get("feature_id")
                )
                reason = _normalize_feature_memory_text(action.get("reason"))
                if label and reason:
                    action_labels.append(f"{label}({reason})")
                elif label:
                    action_labels.append(label)
            if action_labels:
                assistant_parts.append("下一步: " + "；".join(action_labels))

    user_text = _truncate_feature_memory_text(
        "；".join(list(dict.fromkeys(user_parts))[:5]),
        _FEATURE_MEMORY_LINE_MAX_CHARS,
    )
    assistant_text = _truncate_feature_memory_text(
        "；".join(list(dict.fromkeys(assistant_parts))[:5]),
        _FEATURE_MEMORY_LINE_MAX_CHARS,
    )

    lines: list[str] = []
    if user_text:
        lines.append(f"user: {user_text}")
    if assistant_text:
        lines.append(f"assistant: {assistant_text}")

    conversation_text = "\n".join(lines).strip()
    if not conversation_text:
        return ""
    if len(conversation_text) <= _FEATURE_MEMORY_TEXT_MAX_CHARS:
        return conversation_text
    return _truncate_feature_memory_text(conversation_text, _FEATURE_MEMORY_TEXT_MAX_CHARS)


async def _try_langgraph_execution(
    workspace_type: str,
    feature_id: str,
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Attempt LangGraph sub-graph execution and surface the root cause on failure."""
    from src.agents.feature_leader import get_feature_leader_runtime

    user_id = payload.get("user_id") or payload.get("created_by")
    params = _read_params(payload)

    runtime = build_feature_runtime(feature_id, payload, params)

    try:
        if runtime is not None:
            initial_phase = str(runtime.get("current_phase") or "")
            next_phase = resolve_runtime_next_phase(feature_id, params)
            if initial_phase and next_phase and initial_phase != next_phase:
                advance_runtime_phase(runtime, initial_phase, next_phase)
            append_runtime_activity(
                runtime,
                title="任务启动",
                description="正在准备参数并启动增强执行。",
            )
            await progress.update(
                8,
                "启动 LangGraph 增强处理",
                current_step=runtime.get("current_phase"),
                metadata={"runtime": runtime},
                stage_transition=True,
            )
        else:
            await progress.update(5, "启动 LangGraph 增强处理")

        progress_token = bind_progress_tracker(progress)
        runtime_token = bind_runtime_state(runtime) if runtime is not None else None
        try:
            result = await get_feature_leader_runtime().execute_feature(
                workspace_type=workspace_type,
                feature_id=feature_id,
                payload=payload,
                user_id=str(user_id) if user_id else None,
            )
        finally:
            reset_progress_tracker(progress_token)
            if runtime_token is not None:
                reset_runtime_state(runtime_token)

        quality_report = evaluate_feature_output_quality(
            workspace_type=workspace_type,
            feature_id=feature_id,
            result=result,
        )
        quality_status = str(quality_report.get("status") or "unknown")
        if quality_status == "fail":
            quality_summary = str(quality_report.get("summary") or "feature output quality gate failed")
            raise RuntimeError(
                f"feature_quality_gate_failed: {workspace_type}.{feature_id}: {quality_summary}"
            )

        artifacts = await _persist_langgraph_artifacts(
            feature_id, workspace_type, payload, result
        )

        if runtime is not None:
            current_phase = runtime.get("current_phase")
            if current_phase:
                advance_runtime_phase(runtime, str(current_phase), None)
            enrich_runtime_with_result(
                feature_id,
                runtime,
                result,
                artifacts,
                quality_report=quality_report,
            )

        # Wrap result in standard feature response format
        wrapped = {
            "success": True,
            "feature_id": feature_id,
            "feature_name": payload.get("feature_name", feature_id),
            "workspace_type": workspace_type,
            "handler_key": payload.get("handler_key", f"{workspace_type}.{feature_id}"),
            "generation_mode": result.get("generation_mode", "llm"),
            "message": f"{feature_id} 已通过 LangGraph 增强完成",
            "data": result,
            "artifacts": artifacts,
            "refresh_targets": ["artifacts"],
            "generated_at": result.get("generated_at", datetime.now(tz=UTC).isoformat()),
        }
        if runtime is not None:
            wrapped["runtime"] = runtime
            await progress.update(
                max(runtime_progress_for_phase(runtime), 98),
                "LangGraph 增强处理完成",
                current_step=runtime.get("current_phase"),
                metadata={"runtime": runtime},
                stage_transition=True,
            )
        else:
            await progress.update(100, "LangGraph 增强处理完成")
        wrapped["quality"] = quality_report
        return wrapped
    except Exception as exc:
        logger.warning(
            "LangGraph execution failed for feature '%s' in workspace '%s'",
            feature_id,
            workspace_type,
            exc_info=True,
        )
        detail = str(exc).strip() or exc.__class__.__name__
        raise RuntimeError(
            f"LangGraph execution failed for feature '{feature_id}' "
            f"in workspace '{workspace_type}': {detail}"
        ) from exc


def _schedule_memory_extraction(
    workspace_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Schedule async memory extraction (fire-and-forget)."""
    user_id = payload.get("user_id") or payload.get("created_by")
    if not user_id:
        return

    workspace_id = payload.get("workspace_id")
    feature_id = payload.get("feature_id", "")
    conversation_text = _build_feature_memory_conversation(
        workspace_type,
        payload,
        result,
    )
    if not conversation_text:
        return

    async def _extract():
        try:
            from src.services.user_memory_service import extract_and_persist_knowledge

            await extract_and_persist_knowledge(
                str(user_id),
                conversation_text,
                workspace_context=str(workspace_id) if workspace_id else None,
                source=f"feature:{workspace_type}.{feature_id}",
            )
        except Exception:
            logger.debug("Memory extraction failed for feature %s", feature_id, exc_info=True)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_extract())
    except RuntimeError:
        pass


async def execute_workspace_feature(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Execute a workspace feature through the feature leader runtime."""
    workspace_type = str(payload.get("workspace_type") or "")
    feature_id = str(payload.get("feature_id") or "")

    # Validate feature exists in registry
    feature = get_workspace_feature(workspace_type, feature_id)
    if not feature:
        raise ValueError(
            f"Unknown workspace feature '{feature_id}' for workspace type '{workspace_type}'"
        )

    effective_payload = payload
    if workspace_type == "thesis" and feature_id == "thesis_writing":
        effective_payload = _with_normalized_thesis_writing_payload(payload)
        action = str(_read_params(effective_payload).get("action") or "")
        if action not in _THESIS_WRITING_LANGGRAPH_ACTIONS:
            raise ValueError(
                f"Unsupported thesis_writing action: {action}"
            )

    # Try LangGraph sub-graph execution and collect all model usage for billing.
    usage_token = bind_token_usage_collector()
    try:
        result = await _try_langgraph_execution(
            workspace_type,
            feature_id,
            effective_payload,
            progress,
        )
        usage = get_collected_token_usage()
    finally:
        reset_token_usage_collector(usage_token)

    if usage is not None:
        result["token_usage"] = usage.as_dict()

    _schedule_memory_extraction(workspace_type, effective_payload, result)
    return result
