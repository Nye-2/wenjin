"""Tests for capability compiler (Task 2.4)."""

from typing import TypedDict

import pytest

# Ensure subagent types are registered before importing compiler
import src.subagents.v2.types  # noqa: F401
from src.agents.lead_agent.v2.compiler import _default_runner_factory, compile_graph
from src.agents.lead_agent.v2.runtime import ExecutionAborted
from src.subagents.v2.base import SubagentContext, SubagentResult


class CompilerState(TypedDict, total=False):
    node_results: dict
    workspace_id: str
    execution_id: str
    inputs_for_tasks: dict
    workspace_data: dict
    capability_policy: dict


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SINGLE_PHASE_TEMPLATE = {
    "phases": [
        {
            "name": "outline",
            "tasks": [
                {"name": "make_outline", "subagent_type": "react"},
            ],
        }
    ]
}

TWO_PHASE_SERIAL_TEMPLATE = {
    "phases": [
        {
            "name": "discover",
            "tasks": [
                {"name": "search", "subagent_type": "searcher"},
            ],
        },
        {
            "name": "write",
            "depends_on": ["discover"],
            "tasks": [
                {"name": "outline", "subagent_type": "react"},
            ],
        },
    ]
}

PARALLEL_TASKS_TEMPLATE = {
    "phases": [
        {
            "name": "search",
            "tasks": [
                {"name": "search_a", "subagent_type": "searcher"},
                {"name": "search_b", "subagent_type": "searcher"},
            ],
        },
        {
            "name": "write",
            "depends_on": ["search"],
            "tasks": [
                {"name": "outline", "subagent_type": "react"},
            ],
        },
    ]
}


def _make_state(
    inputs_for_tasks: dict | None = None,
    workspace_id: str = "ws-test",
    execution_id: str = "exec-test",
    capability_policy: dict | None = None,
) -> CompilerState:
    return CompilerState(
        workspace_id=workspace_id,
        execution_id=execution_id,
        inputs_for_tasks=inputs_for_tasks or {},
        workspace_data={},
        node_results={},
        capability_policy=capability_policy or {},
    )


# ---------------------------------------------------------------------------
# test_compile_single_phase_single_task
# ---------------------------------------------------------------------------


def test_compile_single_phase_single_task():
    """Compiling a 1-phase, 1-task template yields a graph with that 1 node."""
    graph = compile_graph(SINGLE_PHASE_TEMPLATE, state_class=CompilerState)
    # The compiled graph should have the node available — check via graph.nodes attr
    node_names = set(graph.nodes)
    assert "outline__make_outline" in node_names


# ---------------------------------------------------------------------------
# test_compile_two_phases_serial
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compile_two_phases_serial():
    """Two serial phases: discover → write. Both subagents must be called."""
    execution_order = []

    async def mock_discover(ctx):
        execution_order.append("search")
        return SubagentResult(output={"papers": []})

    async def mock_write(ctx):
        execution_order.append("outline")
        return SubagentResult(output={"outline": []})

    def runner_factory(subagent_cls, task_spec):
        name = task_spec["name"]

        async def run_node(state):
            ctx = SubagentContext(
                workspace_id=state.get("workspace_id", ""),
                execution_id=state.get("execution_id", ""),
                prompt=task_spec.get("prompt_template", ""),
                inputs=state.get("inputs_for_tasks", {}).get(name, {}),
                tools=task_spec.get("tools", []),
                workspace_data=state.get("workspace_data", {}),
            )
            if name == "search":
                result = await mock_discover(ctx)
            else:
                result = await mock_write(ctx)
            node_results = dict(state.get("node_results", {}))
            node_results[name] = {"output": result.output}
            return {"node_results": node_results}

        return run_node

    graph = compile_graph(
        TWO_PHASE_SERIAL_TEMPLATE,
        state_class=CompilerState,
        runner_factory=runner_factory,
    )
    initial = _make_state()
    await graph.ainvoke(initial)

    # Both tasks must have run
    assert "search" in execution_order
    assert "outline" in execution_order
    # discover runs before write
    assert execution_order.index("search") < execution_order.index("outline")


# ---------------------------------------------------------------------------
# test_compile_phase_with_parallel_tasks
# ---------------------------------------------------------------------------


def test_compile_phase_with_parallel_tasks():
    """Two tasks in the same phase are both wired as nodes."""
    graph = compile_graph(PARALLEL_TASKS_TEMPLATE, state_class=CompilerState)
    node_names = set(graph.nodes)
    assert "search__search_a" in node_names
    assert "search__search_b" in node_names
    assert "write__outline" in node_names


# ---------------------------------------------------------------------------
# test_compile_unknown_subagent_raises
# ---------------------------------------------------------------------------


def test_compile_unknown_subagent_raises():
    """An unknown subagent_type must raise KeyError during compilation."""
    template = {
        "phases": [
            {
                "name": "phase1",
                "tasks": [
                    {"name": "task1", "subagent_type": "does_not_exist_xyzzy"},
                ],
            }
        ]
    }
    with pytest.raises(KeyError, match="does_not_exist_xyzzy"):
        compile_graph(template, state_class=CompilerState)


# ---------------------------------------------------------------------------
# test_compile_actually_runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compile_actually_runs():
    """Compile + invoke: real react stub output must appear in node_results."""
    template = {
        "phases": [
            {
                "name": "outline_phase",
                "tasks": [
                    {
                        "name": "make_outline",
                        "subagent_type": "react",
                    }
                ],
            }
        ]
    }

    graph = compile_graph(template, state_class=CompilerState)
    initial = _make_state(inputs_for_tasks={"make_outline": {"topic": "quantum computing"}})
    final_state = await graph.ainvoke(initial)

    assert "make_outline" in final_state["node_results"]
    result = final_state["node_results"]["make_outline"]
    assert "output" in result
    assert "text" in result["output"]


@pytest.mark.asyncio
async def test_default_runner_passes_publish_event_to_subagent_context():
    """Harness tools need the existing execution-event publisher in static graphs."""

    captured_publish = None

    class CapturingSubagent:
        async def run(self, ctx: SubagentContext) -> SubagentResult:
            nonlocal captured_publish
            captured_publish = ctx.publish_event
            return SubagentResult(output={"ok": True})

    async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
        pass

    run_node = _default_runner_factory(
        CapturingSubagent,
        {"name": "capture", "subagent_type": "react"},
        publish_event=publish_event,
    )
    result_state = await run_node(_make_state())

    assert result_state["node_results"]["capture"]["output"] == {"ok": True}
    assert captured_publish is publish_event


@pytest.mark.asyncio
async def test_default_runner_resolves_static_graph_tools_through_harness_policy():
    captured_tools: list[str] = []

    class CapturingSubagent:
        async def run(self, ctx: SubagentContext) -> SubagentResult:
            captured_tools.extend(ctx.tools)
            return SubagentResult(output={"ok": True})

    run_node = _default_runner_factory(
        CapturingSubagent,
        {
            "name": "analysis",
            "subagent_type": "react",
            "_skill": {
                "skill_json": {
                    "sandbox_access": {"mode": "required", "profiles": ["analysis"]},
                },
            },
        },
    )
    await run_node(
        _make_state(
            capability_policy={
                "sandbox_policy": {
                    "mode": "required",
                    "allowed_operations": ["run_python"],
                },
            },
        )
    )

    assert set(captured_tools) >= {
        "sandbox.list_dir",
        "sandbox.glob",
        "sandbox.grep",
        "sandbox.read_file",
        "sandbox.read_output_ref",
        "sandbox.run_python",
    }
    assert "sandbox.generate_figure" not in captured_tools


@pytest.mark.asyncio
async def test_default_runner_fails_when_required_static_graph_tool_is_denied():
    class UnusedSubagent:
        async def run(self, ctx: SubagentContext) -> SubagentResult:
            return SubagentResult(output={"should_not_run": True})

    run_node = _default_runner_factory(
        UnusedSubagent,
        {
            "name": "writer",
            "subagent_type": "react",
            "required_tools": ["sandbox.write_file"],
            "_skill": {"allowed_tools": ["sandbox.write_file"]},
        },
    )
    result_state = await run_node(
        _make_state(
            capability_policy={
                "allowed_tools": ["sandbox.read_file"],
                "permissions": ["filesystem.read"],
            },
        )
    )

    assert "required static graph tools denied by harness policy" in (
        result_state["node_results"]["writer"]["error"]
    )


@pytest.mark.asyncio
async def test_default_runner_marks_subagent_timeout_as_node_error():
    class HangingSubagent:
        async def run(self, ctx: SubagentContext) -> SubagentResult:
            import asyncio

            await asyncio.sleep(1)
            return SubagentResult(output={"too_late": True})

    run_node = _default_runner_factory(
        HangingSubagent,
        {
            "name": "slow",
            "subagent_type": "react",
            "timeout_seconds": 0.01,
        },
    )
    result_state = await run_node(_make_state())

    assert "timed out after" in result_state["node_results"]["slow"]["error"]


@pytest.mark.asyncio
async def test_default_runner_raises_execution_aborted_during_subagent_run():
    class HangingSubagent:
        async def run(self, ctx: SubagentContext) -> SubagentResult:
            import asyncio

            await asyncio.sleep(1)
            return SubagentResult(output={"too_late": True})

    async def abort_check() -> bool:
        return True

    run_node = _default_runner_factory(
        HangingSubagent,
        {"name": "slow", "subagent_type": "react"},
        abort_check=abort_check,
        abort_exc=ExecutionAborted,
    )

    with pytest.raises(ExecutionAborted):
        await run_node(_make_state())
