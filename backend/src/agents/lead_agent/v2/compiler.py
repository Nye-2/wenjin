"""Capability compiler — converts a capability graph_template into a LangGraph StateGraph."""

import asyncio
from typing import Callable

from langgraph.graph import END, START, StateGraph

from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import REGISTRY
# Importing types populates REGISTRY with all v2 subagent classes
from src.subagents.v2 import types as _types  # noqa: F401


def compile_graph(
    template: dict,
    *,
    state_class: type,
    runner_factory: Callable[[type[SubagentBase], dict], Callable] | None = None,
    abort_check: Callable | None = None,
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

    Returns:
        A compiled LangGraph CompiledStateGraph ready for invocation.

    Raises:
        KeyError: If a task's subagent_type is not registered in the global REGISTRY.
    """
    from src.agents.lead_agent.v2.runtime import ExecutionAborted

    builder = StateGraph(state_class)
    factory = runner_factory or _default_runner_factory

    # 1. Add a node per task, named "{phase}__{task}"
    nodes_by_phase: dict[str, list[str]] = {}
    for phase in template["phases"]:
        nodes_by_phase[phase["name"]] = []
        for task in phase["tasks"]:
            node_name = f"{phase['name']}__{task['name']}"
            subagent_cls = REGISTRY.get(task["subagent_type"])  # raises KeyError if unknown
            node_fn = factory(subagent_cls, task)
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


def _default_runner_factory(subagent_cls: type[SubagentBase], task_spec: dict) -> Callable:
    """Build a default async node function that runs the subagent and stores results.

    Supports retry via ``retry_on_failure`` in task_spec (default 0 extra retries).
    On final failure, stores ``{"error": "<message>"}`` in node_results instead of
    raising — this allows downstream nodes to continue running (failed_partial status).
    """
    import asyncio

    _max_attempts = (task_spec.get("retry_on_failure") or 0) + 1
    _task_name = task_spec["name"]

    async def run_node(state: dict) -> dict:
        ctx = SubagentContext(
            workspace_id=state.get("workspace_id", ""),
            execution_id=state.get("execution_id", ""),
            prompt=task_spec.get("prompt_template", ""),
            inputs=state.get("inputs_for_tasks", {}).get(_task_name, {}),
            tools=task_spec.get("tools", []),
            workspace_data=state.get("workspace_data", {}),
        )
        last_error: Exception | None = None
        for attempt in range(_max_attempts):
            try:
                result: SubagentResult = await subagent_cls().run(ctx)
                node_results = dict(state.get("node_results", {}))
                node_results[_task_name] = {
                    "output": result.output,
                    "thinking": result.thinking,
                    "tool_calls": result.tool_calls,
                    "token_usage": result.token_usage,
                }
                return {"node_results": node_results}
            except Exception as exc:
                last_error = exc
                if attempt < _max_attempts - 1:
                    await asyncio.sleep(2**attempt)

        # All attempts failed — record error, don't raise (let graph continue)
        node_results = dict(state.get("node_results", {}))
        node_results[_task_name] = {"error": str(last_error)}
        return {"node_results": node_results}

    return run_node


def _wrap_with_abort_check(node_fn: Callable, abort_check: Callable, abort_exc: type) -> Callable:
    """Wrap a node function to check for abort signal before execution."""

    async def wrapped(state: dict) -> dict:
        if await abort_check():
            raise abort_exc("abort signal detected")
        return await node_fn(state)

    return wrapped
