"""Tests for feature leader dynamic workflow planning and runtime orchestration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.feature_leader.runtime import FeatureLeaderRuntime
from src.agents.feature_leader.workflow import (
    FeatureWorkflowPlan,
    build_dynamic_feature_workflow_plan,
)
from src.subagents.parallel import ExecutionPhase, PhasedPlan, PhaseResult


def _enabled_app_config(max_concurrent: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        subagents=SimpleNamespace(enabled=True, max_concurrent=max_concurrent)
    )


def test_build_dynamic_plan_for_deep_research() -> None:
    plan = build_dynamic_feature_workflow_plan(
        workspace_type="thesis",
        feature_id="deep_research",
        payload={"params": {"topic": "多模态医学影像分割"}},
    )

    assert isinstance(plan, FeatureWorkflowPlan)
    assert plan.strategy == "deep_research:research_discovery"
    assert plan.phase_count == 2
    assert plan.task_count == 4
    assert plan.phased_plan.phases[0].name == "discovery"
    assert any(
        task.get("subagent_type") == "scout"
        for task in plan.phased_plan.phases[0].tasks
    )


def test_build_dynamic_plan_skips_lightweight_thesis_review() -> None:
    plan = build_dynamic_feature_workflow_plan(
        workspace_type="thesis",
        feature_id="thesis_writing",
        payload={"params": {"action": "review_section"}},
    )

    assert plan is None


def test_build_dynamic_plan_for_figure_generation() -> None:
    plan = build_dynamic_feature_workflow_plan(
        workspace_type="proposal",
        feature_id="figure_generation",
        payload={"params": {"topic": "技术路线图"}},
    )

    assert isinstance(plan, FeatureWorkflowPlan)
    assert plan.strategy == "figure_generation:figure_design_review"
    assert plan.phase_count == 1
    assert plan.task_count == 2
    assert any(
        task.get("subagent_type") == "figure_planner"
        for task in plan.phased_plan.phases[0].tasks
    )


@pytest.mark.asyncio
async def test_runtime_executes_feature_without_workflow_for_non_complex_feature() -> None:
    runtime = FeatureLeaderRuntime()
    payload = {
        "workspace_id": "ws-1",
        "thread_id": "thread-1",
        "params": {"paper_title": "Agent Systems"},
    }

    with patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(return_value={"message": "ok"}),
    ) as execute_feature_graph:
        result = await runtime.execute_feature(
            workspace_type="sci",
            feature_id="framework_outline",
            payload=payload,
            user_id="user-1",
        )

    assert result == {"message": "ok"}
    called_payload = execute_feature_graph.await_args.args[2]
    assert called_payload == payload
    assert "__leader_workflow" not in called_payload["params"]


@pytest.mark.asyncio
async def test_runtime_executes_dynamic_workflow_and_injects_context(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FeatureLeaderRuntime()
    payload = {
        "workspace_id": "ws-1",
        "thread_id": "thread-1",
        "execution_session_id": "exec-1",
        "user_id": "user-1",
        "params": {"topic": "LLM planning"},
    }
    plan = FeatureWorkflowPlan(
        strategy="deep_research:research_discovery",
        phased_plan=PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "search"}],
                ),
            ],
        ),
    )
    fake_executor = SimpleNamespace(
        execute_plan=AsyncMock(
            return_value=[
                PhaseResult(
                    phase_name="discovery",
                    task_results=[
                        {
                            "subagent_type": "scout",
                            "success": True,
                            "result": {"papers": [{"title": "Paper A"}]},
                            "error": None,
                        }
                    ],
                )
            ]
        )
    )

    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.get_app_config",
        lambda: _enabled_app_config(4),
    )
    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.build_dynamic_feature_workflow_plan",
        lambda **kwargs: plan,
    )
    monkeypatch.setattr(runtime, "_build_executor", lambda _payload: fake_executor)

    with patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(return_value={"message": "ok"}),
    ) as execute_feature_graph:
        result = await runtime.execute_feature(
            workspace_type="thesis",
            feature_id="deep_research",
            payload=payload,
            user_id="user-1",
        )

    assert result["message"] == "ok"
    assert result["leader_workflow"]["status"] == "completed"
    called_payload = execute_feature_graph.await_args.args[2]
    assert called_payload["params"]["__leader_workflow"]["status"] == "completed"
    assert called_payload["params"]["__leader_workflow"]["strategy"] == "deep_research:research_discovery"
    assert "__leader_workflow_highlights" in called_payload["params"]
    assert callable(fake_executor.execute_plan.await_args.kwargs["phase_callback"])


@pytest.mark.asyncio
async def test_runtime_falls_back_when_workflow_execution_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FeatureLeaderRuntime()
    payload = {
        "workspace_id": "ws-1",
        "thread_id": "thread-1",
        "execution_session_id": "exec-1",
        "user_id": "user-1",
        "params": {"topic": "LLM planning"},
    }
    plan = FeatureWorkflowPlan(
        strategy="deep_research:research_discovery",
        phased_plan=PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "search"}],
                ),
            ],
        ),
    )
    fake_executor = SimpleNamespace(
        execute_plan=AsyncMock(side_effect=RuntimeError("subagent crashed"))
    )

    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.get_app_config",
        lambda: _enabled_app_config(4),
    )
    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.build_dynamic_feature_workflow_plan",
        lambda **kwargs: plan,
    )
    monkeypatch.setattr(runtime, "_build_executor", lambda _payload: fake_executor)

    with patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(return_value={"message": "ok"}),
    ) as execute_feature_graph:
        result = await runtime.execute_feature(
            workspace_type="thesis",
            feature_id="deep_research",
            payload=payload,
            user_id="user-1",
        )

    assert result["message"] == "ok"
    assert result["leader_workflow"]["status"] == "failed"
    assert "feature_leader_workflow_failed" in str(result["leader_workflow"].get("error") or "")
    called_payload = execute_feature_graph.await_args.args[2]
    assert called_payload["params"]["__leader_workflow"]["status"] == "failed"


@pytest.mark.asyncio
async def test_runtime_generates_execution_session_for_complex_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FeatureLeaderRuntime()
    payload = {
        "workspace_id": "ws-1",
        "thread_id": "thread-1",
        "params": {"topic": "LLM planning"},
    }
    plan = FeatureWorkflowPlan(
        strategy="deep_research:research_discovery",
        phased_plan=PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "search"}],
                ),
            ],
        ),
    )
    fake_executor = SimpleNamespace(
        execute_plan=AsyncMock(
            return_value=[
                PhaseResult(
                    phase_name="discovery",
                    task_results=[
                        {
                            "subagent_type": "scout",
                            "success": True,
                            "result": {"papers": [{"title": "Paper A"}]},
                            "error": None,
                        }
                    ],
                )
            ]
        )
    )
    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.get_app_config",
        lambda: _enabled_app_config(4),
    )
    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.build_dynamic_feature_workflow_plan",
        lambda **kwargs: plan,
    )
    monkeypatch.setattr(runtime, "_build_executor", lambda _payload: fake_executor)

    with patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(return_value={"message": "ok"}),
    ) as execute_feature_graph:
        result = await runtime.execute_feature(
            workspace_type="thesis",
            feature_id="deep_research",
            payload=payload,
            user_id="user-1",
        )

    assert result["message"] == "ok"
    assert result["leader_workflow"]["status"] == "completed"
    called_context = fake_executor.execute_plan.await_args.kwargs["context"]
    assert str(called_context.get("execution_session_id", "")).startswith("adhoc-")
    execute_feature_graph.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_emits_runtime_updates_during_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FeatureLeaderRuntime()
    payload = {
        "workspace_id": "ws-1",
        "thread_id": "thread-1",
        "execution_session_id": "exec-1",
        "user_id": "user-1",
        "params": {"topic": "LLM planning"},
    }
    plan = FeatureWorkflowPlan(
        strategy="deep_research:research_discovery",
        phased_plan=PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "scout", "prompt": "search"}],
                ),
            ],
        ),
    )
    runtime_state = {
        "current_phase": "discovery",
        "phases": [],
        "blocks": [],
    }

    class _Executor:
        def __init__(self) -> None:
            self.phase_callback_seen = False

        async def execute_plan(self, _plan, *, context=None, phase_callback=None):
            _ = context
            self.phase_callback_seen = callable(phase_callback)
            phase_result = PhaseResult(
                phase_name="discovery",
                task_results=[
                    {
                        "subagent_type": "scout",
                        "success": True,
                        "result": {"papers": [{"title": "Paper A"}]},
                        "error": None,
                    }
                ],
            )
            if callable(phase_callback):
                await phase_callback(phase_result)
            return [phase_result]

    fake_executor = _Executor()

    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.get_app_config",
        lambda: _enabled_app_config(4),
    )
    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.build_dynamic_feature_workflow_plan",
        lambda **kwargs: plan,
    )
    monkeypatch.setattr(runtime, "_build_executor", lambda _payload: fake_executor)
    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.get_runtime_state",
        lambda: runtime_state,
    )

    with patch(
        "src.agents.feature_leader.runtime._emit_bound_runtime",
        new=AsyncMock(),
    ) as emit_bound_runtime, patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(return_value={"message": "ok"}),
    ):
        result = await runtime.execute_feature(
            workspace_type="thesis",
            feature_id="deep_research",
            payload=payload,
            user_id="user-1",
        )

    assert result["leader_workflow"]["status"] == "completed"
    assert fake_executor.phase_callback_seen is True
    assert emit_bound_runtime.await_count >= 2
    block_ids = {
        block.get("id")
        for block in runtime_state["blocks"]
        if isinstance(block, dict)
    }
    assert "leader-workflow" in block_ids
    assert "leader-workflow-phases" in block_ids
