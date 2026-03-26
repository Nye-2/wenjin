"""Unified workspace feature execution handler.

All workspace types now route through workspace_lead_agent.execute_feature_graph.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

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

logger = logging.getLogger(__name__)

_THESIS_WRITING_LANGGRAPH_ACTIONS = {
    "generate_outline",
    "write_chapter",
    "write_all",
    "review_section",
    "revise_section",
    "review_and_revise",
}


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


async def _try_langgraph_execution(
    workspace_type: str,
    feature_id: str,
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Attempt LangGraph sub-graph execution and surface the root cause on failure."""
    from src.agents.workspace_lead_agent import execute_feature_graph

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
            result = await execute_feature_graph(
                workspace_type,
                feature_id,
                payload,
                user_id=str(user_id) if user_id else None,
            )
        finally:
            reset_progress_tracker(progress_token)
            if runtime_token is not None:
                reset_runtime_state(runtime_token)
        artifacts = await _persist_langgraph_artifacts(
            feature_id, workspace_type, payload, result
        )

        if runtime is not None:
            current_phase = runtime.get("current_phase")
            if current_phase:
                advance_runtime_phase(runtime, str(current_phase), None)
            enrich_runtime_with_result(feature_id, runtime, result, artifacts)

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

    summary_parts = [
        f"Workspace: {workspace_type}",
        f"Feature: {feature_id}",
        f"Result mode: {result.get('generation_mode', 'unknown')}",
    ]
    message = result.get("message", "")
    if message:
        summary_parts.append(f"Output: {message}")

    conversation_text = "; ".join(summary_parts)

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
    """Execute a workspace feature using LangGraph sub-graphs.

    All workspace types now route through workspace_lead_agent.execute_feature_graph.
    """
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

    # Try LangGraph sub-graph execution
    result = await _try_langgraph_execution(
        workspace_type,
        feature_id,
        effective_payload,
        progress,
    )

    _schedule_memory_extraction(workspace_type, effective_payload, result)
    return result
