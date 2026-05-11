"""Tests for capability compiler (Task 2.4)."""

from typing import TypedDict
from unittest.mock import AsyncMock, patch

import pytest

# Ensure subagent types are registered before importing compiler
import src.subagents.v2.types  # noqa: F401

from src.agents.lead_agent.v2.compiler import compile_graph
from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import REGISTRY


class TestState(TypedDict, total=False):
    node_results: dict
    workspace_id: str
    execution_id: str
    inputs_for_tasks: dict
    workspace_data: dict


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
) -> TestState:
    return TestState(
        workspace_id=workspace_id,
        execution_id=execution_id,
        inputs_for_tasks=inputs_for_tasks or {},
        workspace_data={},
        node_results={},
    )


# ---------------------------------------------------------------------------
# test_compile_single_phase_single_task
# ---------------------------------------------------------------------------


def test_compile_single_phase_single_task():
    """Compiling a 1-phase, 1-task template yields a graph with that 1 node."""
    graph = compile_graph(SINGLE_PHASE_TEMPLATE, state_class=TestState)
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
        state_class=TestState,
        runner_factory=runner_factory,
    )
    initial = _make_state()
    final_state = await graph.ainvoke(initial)

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
    graph = compile_graph(PARALLEL_TASKS_TEMPLATE, state_class=TestState)
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
        compile_graph(template, state_class=TestState)


# ---------------------------------------------------------------------------
# test_compile_actually_runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compile_actually_runs():
    """Compile + invoke: real outliner stub output must appear in node_results."""
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

    graph = compile_graph(template, state_class=TestState)
    initial = _make_state(inputs_for_tasks={"make_outline": {"topic": "quantum computing"}})
    final_state = await graph.ainvoke(initial)

    assert "make_outline" in final_state["node_results"]
    result = final_state["node_results"]["make_outline"]
    assert "output" in result
    assert "text" in result["output"]
