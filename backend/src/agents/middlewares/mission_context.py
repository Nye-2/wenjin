"""Prompt-state mission context middleware for chat follow-up turns."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState
_MISSION_CONTEXT_CHAR_LIMIT = 2000
_ACTIVE_EXECUTION_STATUSES = frozenset({"running", "pending", "awaiting_user_input"})
_STATUS_LABELS = {
    "running": "进行中",
    "pending": "排队中",
    "awaiting_user_input": "等待用户确认",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
}


def _string(value: Any, *, max_chars: int | None = None) -> str:
    text = str(value or "").strip()
    if max_chars is not None and len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _compact_lines(lines: list[str]) -> str:
    text = "\n".join(line for line in lines if line.strip()).strip()
    if len(text) <= _MISSION_CONTEXT_CHAR_LIMIT:
        return text
    suffix = "\n...[truncated]"
    budget = max(0, _MISSION_CONTEXT_CHAR_LIMIT - len(suffix))
    return text[:budget].rstrip() + suffix


def _capability_name(
    execution: Any,
    capability_names: Mapping[str, str],
) -> str:
    display_name = _string(getattr(execution, "display_name", None), max_chars=80)
    if display_name:
        return display_name
    capability_id = _string(getattr(execution, "capability_id", None), max_chars=80)
    return capability_names.get(capability_id, capability_id)


def _first_scalar(data: Mapping[str, Any] | None, keys: tuple[str, ...]) -> str:
    if not isinstance(data, Mapping):
        return ""
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _derived_goal(execution: Any, capability_name: str) -> str:
    brief = getattr(execution, "task_brief_json", None)
    goal = _first_scalar(
        brief if isinstance(brief, Mapping) else None,
        (
            "goal",
            "objective",
            "topic",
            "title",
            "research_question",
            "question",
            "raw_message",
            "user_request",
        ),
    )
    return _string(goal or capability_name, max_chars=140)


def _current_stage(execution: Any) -> str:
    graph = getattr(execution, "graph_json", None)
    node_states = getattr(execution, "node_states_json", None)
    if not isinstance(graph, Mapping) or not isinstance(node_states, Mapping):
        return ""
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return ""
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        node_id = _string(node.get("id"))
        if not node_id:
            continue
        node_state = node_states.get(node_id)
        if isinstance(node_state, Mapping) and _string(node_state.get("status")) == "running":
            return _string(node.get("phase"), max_chars=80)
    return ""


def _string_list(value: Any, *, limit: int, max_chars: int) -> list[str]:
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, list):
        candidates = [str(item or "").strip() for item in value]
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = _string(candidate, max_chars=max_chars)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _open_questions(execution: Any) -> list[str]:
    result = getattr(execution, "result_json", None)
    if isinstance(result, Mapping):
        for key in ("open_questions", "pending_questions", "uncertainties"):
            items = _string_list(result.get(key), limit=2, max_chars=100)
            if items:
                return items
    runtime_state = getattr(execution, "runtime_state_json", None)
    if isinstance(runtime_state, Mapping):
        for key in ("open_questions", "pending_questions", "uncertainties"):
            items = _string_list(runtime_state.get(key), limit=2, max_chars=100)
            if items:
                return items
    return []


def _next_actions(execution: Any) -> list[str]:
    actions = getattr(execution, "next_actions", None)
    result: list[str] = []
    for item in actions or []:
        if isinstance(item, Mapping):
            label = _string(
                item.get("label") or item.get("title") or item.get("summary"),
                max_chars=100,
            )
            if label:
                result.append(label)
        elif isinstance(item, str) and item.strip():
            result.append(_string(item, max_chars=100))
        if len(result) >= 2:
            break
    return result


def _pending_review_count(execution: Any) -> int:
    result = getattr(execution, "result_json", None)
    if isinstance(result, Mapping):
        raw = result.get("pending_review_count")
        if isinstance(raw, int):
            return max(raw, 0)
        pending_items = result.get("pending_review_items")
        if isinstance(pending_items, list):
            return len(pending_items)
    runtime_state = getattr(execution, "runtime_state_json", None)
    if isinstance(runtime_state, Mapping):
        raw = runtime_state.get("pending_review_count")
        if isinstance(raw, int):
            return max(raw, 0)
    return 0


def _evidence_count(execution: Any) -> int:
    result = getattr(execution, "result_json", None)
    if isinstance(result, Mapping):
        raw = result.get("evidence_count")
        if isinstance(raw, int):
            return max(raw, 0)
        for key in ("evidence_items", "evidence", "evidence_packet"):
            value = result.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


def _summary_text(execution: Any) -> str:
    summary = _string(getattr(execution, "result_summary", None), max_chars=220)
    if not summary:
        return ""
    for marker in ("。", "！", "？", ".", "!", "?", "\n"):
        idx = summary.find(marker)
        if idx >= 0:
            return _string(summary[: idx + 1], max_chars=140)
    return _string(summary, max_chars=140)


def _status_label(execution: Any) -> str:
    status = _string(getattr(execution, "status", None), max_chars=40).lower()
    return _STATUS_LABELS.get(status, status or "未知")


def _updated_timestamp(execution: Any) -> str:
    for attr in ("updated_at", "completed_at", "started_at", "created_at"):
        value = getattr(execution, attr, None)
        text = _string(value, max_chars=40)
        if text:
            return text
    return ""


def _execution_block(
    *,
    tag: str,
    execution: Any,
    capability_names: Mapping[str, str],
) -> list[str]:
    execution_id = _string(getattr(execution, "id", None), max_chars=80)
    capability_name = _capability_name(execution, capability_names)
    goal = _derived_goal(execution, capability_name)
    stage = _current_stage(execution)
    summary = _summary_text(execution)
    questions = _open_questions(execution)
    next_actions = _next_actions(execution)
    pending_review_count = _pending_review_count(execution)
    evidence_count = _evidence_count(execution)
    updated_at = _updated_timestamp(execution)

    lines = [f'  <{tag} execution_id="{execution_id}">']
    lines.append(f"  - capability: {capability_name}")
    lines.append(f"  - goal: {goal}")
    lines.append(f"  - status: {_status_label(execution)}")
    if stage:
        lines.append(f"  - current_stage: {stage}")
    if summary:
        lines.append(f"  - summary: {summary}")
    if questions:
        lines.append(f"  - open_questions: {'；'.join(questions)}")
    if next_actions:
        lines.append(f"  - next_actions: {'；'.join(next_actions)}")
    lines.append(f"  - pending_review_count: {pending_review_count}")
    lines.append(f"  - evidence_count: {evidence_count}")
    if updated_at:
        lines.append(f"  - updated_at: {updated_at}")
    lines.append(f"  </{tag}>")
    return lines


class MissionContextMiddleware(Middleware):
    """Load a bounded mission summary into Chat Agent prompt state."""

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        configurable = dict(config.get("configurable", {}) if isinstance(config, dict) else {})
        workspace_id = _string(configurable.get("workspace_id") or state.get("workspace_id"))
        thread_id = _string(configurable.get("thread_id") or state.get("thread_id"))
        user_id = _string(configurable.get("user_id") or state.get("user_id"))
        execution_id = _string(configurable.get("execution_id"))

        if not execution_id and not thread_id and not workspace_id:
            return {}

        capability_names = {
            _string(item.get("id"), max_chars=80): _string(item.get("display_name"), max_chars=80)
            for item in (state.get("available_capabilities") or [])
            if isinstance(item, Mapping)
        }

        try:
            from src.dataservice_client.provider import dataservice_client

            async with dataservice_client() as client:
                selected_execution = None
                if execution_id:
                    selected_execution = await client.get_execution(execution_id)

                executions = await client.list_executions(
                    workspace_id=workspace_id or None,
                    thread_id=thread_id or None,
                    user_id=user_id or None,
                    limit=8,
                )
        except Exception:
            return {}

        ordered = sorted(
            executions,
            key=lambda item: _updated_timestamp(item),
            reverse=True,
        )
        active_execution = next(
            (
                item
                for item in ordered
                if _string(getattr(item, "status", None)).lower() in _ACTIVE_EXECUTION_STATUSES
            ),
            None,
        )
        if active_execution is None and selected_execution is not None:
            if _string(getattr(selected_execution, "status", None)).lower() in _ACTIVE_EXECUTION_STATUSES:
                active_execution = selected_execution

        if active_execution is None and selected_execution is None:
            return {}

        lines = ["<mission_context>"]
        if active_execution is not None:
            lines.extend(
                _execution_block(
                    tag="active_mission",
                    execution=active_execution,
                    capability_names=capability_names,
                )
            )
        if (
            selected_execution is not None
            and _string(getattr(selected_execution, "id", None))
            != _string(getattr(active_execution, "id", None))
        ):
            lines.extend(
                _execution_block(
                    tag="selected_mission",
                    execution=selected_execution,
                    capability_names=capability_names,
                )
            )
        lines.append("</mission_context>")

        return {"mission_prompt_context": _compact_lines(lines)}
