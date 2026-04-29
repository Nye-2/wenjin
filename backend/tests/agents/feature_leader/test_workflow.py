"""Tests for feature leader dynamic workflow planning and runtime orchestration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.feature_leader.runtime import FeatureLeaderRuntime
from src.agents.feature_leader.workflow import (
    FeatureWorkflowPlan,
    build_dynamic_feature_workflow_plan,
    validate_workflow_plan_against_profile,
)
from src.agents.harness import AgentSessionResult
from src.subagents.parallel import ExecutionPhase, PhasedPlan, PhaseResult
from src.workspace_features import (
    FeatureRuntimeMode,
    FeatureRuntimeProfile,
    get_feature_runtime_profile,
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


def test_workflow_plan_validation_rejects_disallowed_subagent() -> None:
    profile = get_feature_runtime_profile("thesis", "deep_research")
    assert profile is not None
    plan = FeatureWorkflowPlan(
        strategy="deep_research:invalid",
        phased_plan=PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="discovery",
                    tasks=[{"subagent_type": "rogue", "prompt": "search"}],
                ),
            ],
        ),
    )

    with pytest.raises(RuntimeError, match="disallowed_subagents"):
        validate_workflow_plan_against_profile(plan, profile)


def test_workflow_plan_validation_rejects_subagent_count_over_profile_limit() -> None:
    profile = get_feature_runtime_profile("proposal", "figure_generation")
    assert profile is not None
    plan = FeatureWorkflowPlan(
        strategy="figure_generation:too_many",
        phased_plan=PhasedPlan(
            phases=[
                ExecutionPhase(
                    name="figure_design",
                    tasks=[
                        {"subagent_type": "figure_planner", "prompt": "plan"},
                        {"subagent_type": "analyst", "prompt": "analyze"},
                        {"subagent_type": "analyst", "prompt": "analyze again"},
                    ],
                ),
            ],
        ),
    )

    with pytest.raises(RuntimeError, match="max_subagents_exceeded"):
        validate_workflow_plan_against_profile(plan, profile)


def test_runtime_harness_provider_comes_from_profile() -> None:
    runtime = FeatureLeaderRuntime()
    profile = FeatureRuntimeProfile(
        workspace_type="thesis",
        feature_id="deep_research",
        runtime_mode=FeatureRuntimeMode.COMPUTE_AGENTIC,
        allowed_subagents=("scout",),
        max_subagents=1,
        agent_harness_provider="native_wenjin",
    )

    harness = runtime._build_agent_harness({}, profile)

    assert harness.provider == "native_wenjin"


def test_runtime_rejects_unknown_harness_provider() -> None:
    runtime = FeatureLeaderRuntime()
    profile = FeatureRuntimeProfile(
        workspace_type="thesis",
        feature_id="deep_research",
        runtime_mode=FeatureRuntimeMode.COMPUTE_AGENTIC,
        agent_harness_provider="unknown",
    )

    with pytest.raises(ValueError, match="unsupported_agent_harness_provider"):
        runtime._build_agent_harness({}, profile)


@pytest.mark.asyncio
async def test_runtime_executes_feature_without_workflow_for_non_complex_feature() -> None:
    runtime = FeatureLeaderRuntime()
    payload = {
        "workspace_id": "ws-1",
        "thread_id": "thread-1",
        "params": {"paper_title": "Agent Systems"},
    }

    with patch(
        "src.agents.feature_leader.graph_registry.execute_feature_graph",
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
async def test_runtime_executes_dynamic_workflow_and_injects_context(
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
    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.build_dynamic_feature_workflow_plan",
        lambda **kwargs: plan,
    )
    fake_harness = SimpleNamespace(
        run_session=AsyncMock(
            return_value=AgentSessionResult(
                provider="test_harness",
                strategy=plan.strategy,
                phase_results=[
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
                ],
            )
        )
    )
    monkeypatch.setattr(
        runtime,
        "_build_agent_harness",
        lambda _payload, _profile: fake_harness,
    )

    with patch(
        "src.agents.feature_leader.graph_registry.execute_feature_graph",
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
    assert result["leader_workflow"]["provider"] == "test_harness"
    assert result["leader_workflow"]["runtime_profile"]["output_contract"] == "evidence_pack"
    called_payload = execute_feature_graph.await_args.args[2]
    assert called_payload["params"]["__leader_workflow"]["status"] == "completed"
    assert called_payload["params"]["__leader_workflow"]["provider"] == "test_harness"
    assert called_payload["params"]["__leader_workflow"]["strategy"] == "deep_research:research_discovery"
    assert "__leader_workflow_highlights" in called_payload["params"]
    request = fake_harness.run_session.await_args.args[0]
    assert request.context["execution_session_id"] == "exec-1"
    assert callable(request.phase_callback)


@pytest.mark.asyncio
async def test_runtime_fails_fast_when_workflow_execution_fails(
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
    fake_harness = SimpleNamespace(
        run_session=AsyncMock(side_effect=RuntimeError("subagent crashed"))
    )

    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.build_dynamic_feature_workflow_plan",
        lambda **kwargs: plan,
    )
    monkeypatch.setattr(
        runtime,
        "_build_agent_harness",
        lambda _payload, _profile: fake_harness,
    )

    with patch(
        "src.agents.feature_leader.graph_registry.execute_feature_graph",
        new=AsyncMock(return_value={"message": "ok"}),
    ) as execute_feature_graph:
        with pytest.raises(RuntimeError, match="feature_leader_workflow_failed"):
            await runtime.execute_feature(
                workspace_type="thesis",
                feature_id="deep_research",
                payload=payload,
                user_id="user-1",
            )

    execute_feature_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_rejects_agentic_workflow_without_execution_session(
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
    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.build_dynamic_feature_workflow_plan",
        lambda **kwargs: plan,
    )

    with patch(
        "src.agents.feature_leader.graph_registry.execute_feature_graph",
        new=AsyncMock(return_value={"message": "ok"}),
    ) as execute_feature_graph:
        with pytest.raises(
            RuntimeError,
            match="feature_leader_workflow_missing_execution_session_id",
        ):
            await runtime.execute_feature(
                workspace_type="thesis",
                feature_id="deep_research",
                payload=payload,
                user_id="user-1",
            )

    execute_feature_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_emits_runtime_updates_during_workflow(
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
    runtime_state = {
        "current_phase": "discovery",
        "phases": [],
        "blocks": [],
    }

    class _Executor:
        def __init__(self) -> None:
            self.phase_callback_seen = False

        async def run_session(self, request):
            self.phase_callback_seen = callable(request.phase_callback)
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
            if callable(request.phase_callback):
                await request.phase_callback(phase_result)
            return AgentSessionResult(
                provider="test_harness",
                strategy=request.strategy,
                phase_results=[phase_result],
            )

    fake_executor = _Executor()

    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.build_dynamic_feature_workflow_plan",
        lambda **kwargs: plan,
    )
    monkeypatch.setattr(
        runtime,
        "_build_agent_harness",
        lambda _payload, _profile: fake_executor,
    )
    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.get_runtime_state",
        lambda: runtime_state,
    )

    with (
        patch(
            "src.agents.feature_leader.runtime._emit_bound_runtime",
            new=AsyncMock(),
        ) as emit_bound_runtime,
        patch(
            "src.agents.feature_leader.graph_registry.execute_feature_graph",
            new=AsyncMock(return_value={"message": "ok"}),
        ),
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
