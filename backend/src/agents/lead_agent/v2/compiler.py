"""Capability compiler — converts a capability graph_template into a LangGraph StateGraph."""

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agents.harness.tool_names import expand_tool_names
from src.agents.lead_agent.v2.template import (
    build_task_render_context,
    render_template,
)

# Importing types populates REGISTRY with all v2 subagent classes
from src.subagents.v2 import types as _types  # noqa: F401
from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import REGISTRY

logger = logging.getLogger(__name__)
DEFAULT_STATIC_NODE_TIMEOUT_SECONDS = 120.0
STATIC_ABORT_POLL_INTERVAL_SECONDS = 0.05


def compile_graph(
    template: dict,
    *,
    state_class: type,
    runner_factory: Callable[[type[SubagentBase], dict], Callable] | None = None,
    abort_check: Callable | None = None,
    skills: dict[str, Any] | None = None,
    publish_event: Callable | None = None,
):
    """Compile capability graph_template → LangGraph StateGraph.

    The runner_factory parameter lets the caller (LeadAgentRuntime) inject custom
    node-runner construction (e.g., to wrap with event publishing). If not supplied,
    a default runner is used that simply calls subagent.run() and merges output
    into state["node_results"][task_name].

    Args:
        template: A capability graph_template dict with a "phases" list.
        state_class: The TypedDict (or similar) used as LangGraph state.
        runner_factory: Optional callable that takes (subagent_cls, task_spec) and
            returns an async node function. Defaults to _default_runner_factory.
        abort_check: Optional async callable () → bool. If it returns True inside a node,
            an ExecutionAborted exception is raised to halt the graph.
        skills: Optional dict mapping skill_id → catalog skill record, pre-loaded
            by the caller. Tasks with skill_id will have the skill attached.
        publish_event: Optional existing execution-event publisher forwarded to
            default runner subagent contexts.

    Returns:
        A compiled LangGraph CompiledStateGraph ready for invocation.

    Raises:
        KeyError: If a task's subagent_type is not registered in the global REGISTRY.
    """
    from src.agents.lead_agent.v2.runtime import ExecutionAborted

    _skills = skills or {}
    builder = StateGraph(state_class)
    if runner_factory is None:
        def factory(subagent_cls: type[SubagentBase], task_spec: dict) -> Callable:
            return _default_runner_factory(
                subagent_cls,
                task_spec,
                abort_check=abort_check,
                abort_exc=ExecutionAborted,
                publish_event=publish_event,
            )
    else:
        factory = runner_factory

    # Phase → task index used at run time by the renderer to resolve
    # ``{{phases.<phase>.<task>.output.X}}`` references against node_results.
    phase_index: dict[str, list[str]] = {
        phase["name"]: [t["name"] for t in phase["tasks"]]
        for phase in template["phases"]
    }

    # 1. Add a node per task, named "{phase}__{task}"
    nodes_by_phase: dict[str, list[str]] = {}
    for phase in template["phases"]:
        nodes_by_phase[phase["name"]] = []
        for task in phase["tasks"]:
            node_name = f"{phase['name']}__{task['name']}"
            subagent_cls = REGISTRY.get(task["subagent_type"])  # raises KeyError if unknown
            # Attach pre-loaded skill + phase index to task spec for the runner
            task_with_skill = dict(task)
            skill_id = task.get("skill_id")
            if skill_id and skill_id in _skills:
                task_with_skill["_skill"] = _skills[skill_id]
            task_with_skill["_phase_index"] = phase_index
            node_fn = factory(subagent_cls, task_with_skill)
            if abort_check is not None:
                node_fn = _wrap_with_abort_check(node_fn, abort_check, ExecutionAborted)
            builder.add_node(node_name, node_fn)
            nodes_by_phase[phase["name"]].append(node_name)

    # 2. Wire START → root phases (no depends_on)
    roots = [p["name"] for p in template["phases"] if not p.get("depends_on")]
    for phase_name in roots:
        for node in nodes_by_phase[phase_name]:
            builder.add_edge(START, node)

    # 3. Wire phase deps (fan-in / fan-out)
    for phase in template["phases"]:
        for dep in phase.get("depends_on", []):
            for src_node in nodes_by_phase[dep]:
                for dst_node in nodes_by_phase[phase["name"]]:
                    builder.add_edge(src_node, dst_node)

    # 4. Terminal phases (no successor) → END
    has_successor: set[str] = set()
    for phase in template["phases"]:
        for dep in phase.get("depends_on", []):
            has_successor.add(dep)
    for phase_name, names in nodes_by_phase.items():
        if phase_name not in has_successor:
            for n in names:
                builder.add_edge(n, END)

    return builder.compile()


def _default_runner_factory(
    subagent_cls: type[SubagentBase],
    task_spec: dict,
    emit_delta: Callable | None = None,
    publish_event: Callable | None = None,
    abort_check: Callable | None = None,
    abort_exc: type[BaseException] | None = None,
) -> Callable:
    """Build a default async node function that runs the subagent and stores results.

    Supports retry via ``retry_on_failure`` in task_spec (default 0 extra retries).
    On final failure, stores ``{"error": "<message>"}`` in node_results instead of
    raising — this allows downstream nodes to continue running (failed_partial status).

    Args:
        subagent_cls: The subagent class to instantiate and run.
        task_spec: Task specification dict from the capability template.
        emit_delta: Optional async callback ``(event_type, content)`` forwarded
            to SubagentContext for streaming thinking deltas.
        publish_event: Optional existing execution-event publisher forwarded to
            SubagentContext for harness tool events.
    """

    _max_attempts = (task_spec.get("retry_on_failure") or 0) + 1
    _task_name = task_spec["name"]
    _raw_inputs_template = task_spec.get("inputs") or {}
    _phase_index = task_spec.get("_phase_index") or {}

    async def run_node(state: dict) -> dict:
        # Render the task's ``inputs:`` YAML template against the current brief
        # and any upstream task outputs.  Falls back to the raw brief if the
        # capability seed didn't declare an inputs block.
        brief = state.get("inputs_for_tasks", {}).get(_task_name, {})
        if _raw_inputs_template:
            render_ctx = build_task_render_context(
                brief=brief,
                node_results=state.get("node_results", {}),
                phase_index=_phase_index,
            )
            try:
                rendered_inputs = render_template(_raw_inputs_template, render_ctx)
            except Exception:  # pragma: no cover — defensive
                logger.warning(
                    "Input template render failed for task '%s'; falling back to raw brief",
                    _task_name,
                    exc_info=True,
                )
                rendered_inputs = dict(brief)
        else:
            rendered_inputs = dict(brief)
        if isinstance(rendered_inputs, dict):
            user_id = str(state.get("user_id") or "").strip()
            if user_id:
                rendered_inputs.setdefault("user_id", user_id)

        ctx = SubagentContext(
            workspace_id=state.get("workspace_id", ""),
            execution_id=state.get("execution_id", ""),
            prompt=task_spec.get("prompt_template", ""),
            inputs=rendered_inputs,
            tools=task_spec.get("tools", []),
            workspace_data=state.get("workspace_data", {}),
            capability_policy=state.get("capability_policy", {}),
            skill=task_spec.get("_skill"),
            emit_delta=emit_delta,
            publish_event=publish_event,
        )
        try:
            ctx.tools = _resolve_static_graph_tools(ctx, task_spec)
        except Exception as exc:
            node_results = dict(state.get("node_results", {}))
            node_results[_task_name] = {"error": str(exc)}
            return {"node_results": node_results}
        last_error: Exception | None = None
        for attempt in range(_max_attempts):
            try:
                result: SubagentResult = await _run_static_subagent_attempt(
                    subagent_cls().run(ctx),
                    task_name=_task_name,
                    task_spec=task_spec,
                    capability_policy=ctx.capability_policy,
                    skill=ctx.skill,
                    abort_check=abort_check,
                    abort_exc=abort_exc,
                )
                node_results = dict(state.get("node_results", {}))
                node_results[_task_name] = {
                    "output": result.output,
                    "thinking": result.thinking,
                    "tool_calls": result.tool_calls,
                    "token_usage": result.token_usage,
                }
                return {"node_results": node_results}
            except Exception as exc:
                if abort_exc is not None and isinstance(exc, abort_exc):
                    raise
                last_error = exc
                if attempt < _max_attempts - 1:
                    await asyncio.sleep(2**attempt)

        # All attempts failed — record error, don't raise (let graph continue)
        node_results = dict(state.get("node_results", {}))
        node_results[_task_name] = {"error": str(last_error)}
        return {"node_results": node_results}

    return run_node


async def _run_static_subagent_attempt(
    awaitable,
    *,
    task_name: str,
    task_spec: dict[str, Any],
    capability_policy: dict[str, Any],
    skill: Any | None,
    abort_check: Callable | None,
    abort_exc: type[BaseException] | None,
) -> SubagentResult:
    timeout_seconds = _static_node_timeout_seconds(
        task_spec=task_spec,
        capability_policy=capability_policy,
        skill=skill,
    )
    task = asyncio.create_task(awaitable)
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise TimeoutError(
                f"Subagent task {task_name} timed out after {timeout_seconds:g}s"
            )
        done, _ = await asyncio.wait(
            {task},
            timeout=min(STATIC_ABORT_POLL_INTERVAL_SECONDS, remaining),
        )
        if task in done:
            return task.result()
        if abort_check is not None and await _safe_abort_check(abort_check):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            if abort_exc is not None:
                raise abort_exc("abort signal detected")
            raise asyncio.CancelledError("abort signal detected")


async def _safe_abort_check(abort_check: Callable) -> bool:
    try:
        return bool(await abort_check())
    except Exception:
        return False


def _static_node_timeout_seconds(
    *,
    task_spec: dict[str, Any],
    capability_policy: dict[str, Any],
    skill: Any | None,
) -> float:
    configured = (
        task_spec.get("react_timeout_seconds")
        or task_spec.get("timeout_seconds")
        or _mapping_value(capability_policy.get("limits"), "react_timeout_seconds", "timeout_seconds")
        or _mapping_value(
            capability_policy.get("sandbox_policy"),
            "react_timeout_seconds",
            "timeout_seconds",
        )
        or _mapping_value(
            _mapping_value(capability_policy.get("sandbox_policy"), "resource_limits"),
            "react_timeout_seconds",
            "timeout_seconds",
        )
        or _mapping_value(getattr(skill, "config", None), "react_timeout_seconds", "timeout_seconds")
        or _mapping_value(skill.get("config") if isinstance(skill, dict) else None, "react_timeout_seconds", "timeout_seconds")
    )
    try:
        timeout_seconds = float(configured) if configured is not None else DEFAULT_STATIC_NODE_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        timeout_seconds = DEFAULT_STATIC_NODE_TIMEOUT_SECONDS
    return max(0.001, min(timeout_seconds, DEFAULT_STATIC_NODE_TIMEOUT_SECONDS))


def _mapping_value(value: Any, *keys: str) -> Any:
    if not isinstance(value, dict):
        return None
    for key in keys:
        item = value.get(key)
        if item is not None:
            return item
    return None


def _resolve_static_graph_tools(ctx: SubagentContext, task_spec: dict[str, Any]) -> list[str]:
    """Resolve static graph tools through the same harness policy as React."""

    if not _static_graph_declares_tool_policy(ctx, task_spec):
        return []
    requested_tools = list(
        expand_tool_names(
            [
                *_string_list(task_spec.get("tools")),
                *_string_list(task_spec.get("required_tools")),
            ]
        )
    )
    ctx.tools = requested_tools
    from src.agents.harness.langchain_adapter import build_harness_run_context
    from src.agents.harness.policy import resolve_harness_policy

    policy = resolve_harness_policy(build_harness_run_context(ctx))
    required_tools = set(expand_tool_names(_string_list(task_spec.get("required_tools"))))
    denied_required = [tool for tool in required_tools if tool not in policy.allowed_tools]
    if denied_required:
        raise RuntimeError(
            "required static graph tools denied by harness policy: "
            + ", ".join(denied_required)
        )
    return list(policy.allowed_tools)


def _static_graph_declares_tool_policy(ctx: SubagentContext, task_spec: dict[str, Any]) -> bool:
    if _string_list(task_spec.get("tools")) or _string_list(task_spec.get("required_tools")):
        return True
    if _capability_declares_tools(ctx.capability_policy):
        return True
    return _skill_declares_tools(ctx.skill)


def _capability_declares_tools(policy: Any) -> bool:
    if not isinstance(policy, dict):
        return False
    for key in ("allowed_tools", "capability_tools", "tools", "permissions", "allowed_permissions"):
        if _string_list(policy.get(key)):
            return True
    runtime = policy.get("runtime")
    if isinstance(runtime, dict) and _string_list(runtime.get("allowed_tools")):
        return True
    tool_policy = policy.get("tool_policy")
    if isinstance(tool_policy, dict) and _string_list(tool_policy.get("allowed_tools")):
        return True
    sandbox_policy = policy.get("sandbox_policy")
    if isinstance(sandbox_policy, dict):
        mode = str(sandbox_policy.get("mode") or "").strip().lower()
        if mode == "required" or _string_list(sandbox_policy.get("allowed_operations")):
            return True
    return False


def _skill_declares_tools(skill: Any) -> bool:
    if not skill:
        return False
    if isinstance(skill, dict):
        if "allowed_tools" in skill or _string_list(skill.get("allowed_tools")):
            return True
        config = skill.get("config")
        if isinstance(config, dict) and "allowed_tools" in config:
            return True
        skill_json = skill.get("skill_json")
        if isinstance(skill_json, dict) and isinstance(skill_json.get("sandbox_access"), dict):
            return True
        return False
    if _string_list(getattr(skill, "allowed_tools", None)):
        return True
    config = getattr(skill, "config", None)
    return isinstance(config, dict) and (
        "allowed_tools" in config or isinstance(config.get("sandbox_access"), dict)
    )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set, frozenset)):
        raw_items = list(value)
    else:
        return []
    return [text for item in raw_items for text in [str(item).strip()] if text]


def _wrap_with_abort_check(node_fn: Callable, abort_check: Callable, abort_exc: type) -> Callable:
    """Wrap a node function to check for abort signal before execution."""

    async def wrapped(state: dict) -> dict:
        if await abort_check():
            raise abort_exc("abort signal detected")
        return await node_fn(state)

    return wrapped
