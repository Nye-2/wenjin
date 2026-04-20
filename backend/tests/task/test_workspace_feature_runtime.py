"""Runtime coverage tests for workspace feature handler."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.task.handlers.workspace_feature_handler import execute_workspace_feature


@pytest.fixture(autouse=True)
def _stub_feature_workflow_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_execute_plan(
        self: Any,  # noqa: ANN401
        plan: Any,  # noqa: ANN401
        context: dict[str, Any] | None = None,
        phase_callback: Any = None,  # noqa: ANN401
    ) -> list[Any]:  # noqa: ANN401
        _ = context
        from src.subagents.parallel import PhaseResult

        phase_results: list[PhaseResult] = []
        for phase in plan.phases:
            task_results: list[dict[str, Any]] = []
            for task in phase.tasks:
                task_results.append(
                    {
                        "subagent_type": str(task.get("subagent_type") or "general"),
                        "success": True,
                        "result": {"summary": f"{phase.name} done"},
                        "error": None,
                    }
                )
            phase_result = PhaseResult(
                phase_name=str(phase.name),
                task_results=task_results,
            )
            if callable(phase_callback):
                await phase_callback(phase_result)
            phase_results.append(phase_result)
        return phase_results

    monkeypatch.setattr(
        "src.agents.feature_leader.runtime.ParallelExecutor.execute_plan",
        _fake_execute_plan,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workspace_type", "feature_id", "params", "graph_result", "expected_block_ids"),
    [
        (
            "thesis",
            "deep_research",
            {"topic": "Agent planning", "discipline": "computer_science"},
            {
                "generation_mode": "llm",
                "corpus": {"paper_count": 2, "top_papers": [{"title": "Paper A"}]},
                "discovery": {
                    "seminal_works": [{"title": "Seminal"}],
                    "recent_works": [{"title": "Recent"}],
                    "trends": [{"topic": "Trend"}],
                },
                "gaps": [{"description": "Gap A"}],
                "ideas": [{"title": "Idea A", "description": "desc"}],
                "recommended_actions": [{"action": "literature_management", "reason": "next"}],
                "cross_validation": {"validation_score": 8},
            },
            {"research-papers", "research-gaps", "research-ideas", "recommended-actions", "result-summary"},
        ),
        (
            "sci",
            "literature_review",
            {"topic": "Agent planning"},
            {"generation_mode": "llm", "sections": [{"title": "Section A", "content": "content"}]},
            {"review-sections", "result-summary"},
        ),
        (
            "sci",
            "framework_outline",
            {"paper_title": "Agent Paper", "topic": "Agent planning"},
            {"generation_mode": "llm", "sections": [{"title": "Intro", "focus": "Background"}]},
            {"framework-outline", "result-summary"},
        ),
        (
            "sci",
            "peer_review",
            {"paper_title": "Agent Paper", "manuscript_excerpt": "draft"},
            {"generation_mode": "llm", "weaknesses": ["Weakness A"]},
            {"peer-review", "result-summary"},
        ),
        (
            "sci",
            "journal_recommend",
            {"paper_title": "Agent Paper", "abstract": "abstract"},
            {
                "generation_mode": "llm",
                "journals": [{"name": "Journal A", "reason": "fit", "fit": "high"}],
            },
            {"journal-recommendations", "result-summary"},
        ),
        (
            "proposal",
            "experiment_design",
            {"topic": "Agent evaluation", "objective": "Design experiments"},
            {
                "generation_mode": "llm",
                "variables": [{"name": "x", "definition": "var", "type": "independent"}],
            },
            {"experiment-variables", "result-summary"},
        ),
    ],
)
async def test_execute_workspace_feature_emits_runtime_for_feature(
    workspace_type: str,
    feature_id: str,
    params: dict[str, object],
    graph_result: dict[str, object],
    expected_block_ids: set[str],
) -> None:
    progress = AsyncMock()
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": workspace_type,
        "workspace_name": "Workspace Name",
        "workspace_description": "Workspace Description",
        "workspace_discipline": "computer_science",
        "feature_id": feature_id,
        "execution_session_id": "exec-1",
        "params": params,
    }

    with patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(return_value=graph_result),
    ), patch(
        "src.task.handlers.workspace_feature_handler._persist_langgraph_artifacts",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.task.handlers.workspace_feature_handler._schedule_memory_extraction"
    ):
        result = await execute_workspace_feature(payload, progress)

    runtime = result.get("runtime")
    assert isinstance(runtime, dict)
    block_ids = {block.get("id") for block in runtime.get("blocks", []) if isinstance(block, dict)}
    assert expected_block_ids.issubset(block_ids)
    assert runtime.get("current_phase")
    blocks = {
        block.get("id"): block
        for block in runtime.get("blocks", [])
        if isinstance(block, dict) and isinstance(block.get("id"), str)
    }
    phases = runtime.get("phases")
    assert isinstance(phases, list)
    assert phases
    last_phase = phases[-1]
    assert isinstance(last_phase, dict)
    final_phase_id = str(last_phase.get("id") or "").strip()
    assert final_phase_id
    summary_block = blocks.get("result-summary")
    assert isinstance(summary_block, dict)
    assert summary_block.get("phase_id") == final_phase_id

    if feature_id == "deep_research":
        research_papers = blocks.get("research-papers")
        assert isinstance(research_papers, dict)
        assert research_papers.get("phase_id") == "discovery"
        research_gaps = blocks.get("research-gaps")
        assert isinstance(research_gaps, dict)
        assert research_gaps.get("phase_id") == "gap_mining"
        research_ideas = blocks.get("research-ideas")
        assert isinstance(research_ideas, dict)
        assert research_ideas.get("phase_id") == "synthesis"
        recommended_actions = blocks.get("recommended-actions")
        assert isinstance(recommended_actions, dict)
        assert recommended_actions.get("phase_id") == "finalize"


@pytest.mark.asyncio
async def test_execute_workspace_feature_surfaces_langgraph_root_cause() -> None:
    progress = AsyncMock()
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "workspace_name": "Workspace Name",
        "workspace_description": "Workspace Description",
        "workspace_discipline": "computer_science",
        "feature_id": "deep_research",
        "execution_session_id": "exec-1",
        "params": {"topic": "Agent planning"},
    }

    with patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(side_effect=ValueError("planner exploded")),
    ), patch(
        "src.task.handlers.workspace_feature_handler._schedule_memory_extraction"
    ) as mock_schedule:
        with pytest.raises(RuntimeError, match="planner exploded"):
            await execute_workspace_feature(payload, progress)

    mock_schedule.assert_not_called()


@pytest.mark.asyncio
async def test_execute_workspace_feature_projects_leader_workflow_blocks() -> None:
    progress = AsyncMock()
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "workspace_name": "Workspace Name",
        "workspace_description": "Workspace Description",
        "workspace_discipline": "computer_science",
        "feature_id": "deep_research",
        "execution_session_id": "exec-1",
        "params": {"topic": "Agent planning"},
    }
    graph_result = {
        "generation_mode": "llm",
        "summary": "调研输出摘要",
        "ideas": [],
        "gaps": [],
        "leader_workflow": {
            "status": "completed",
            "strategy": "deep_research:research_discovery",
            "phase_count": 2,
            "task_count": 4,
            "phases": [
                {
                    "phase": "discovery",
                    "success": True,
                    "tasks": [
                        {"subagent_type": "scout", "success": True, "result_preview": "paper candidates"},
                        {"subagent_type": "trend_spotter", "success": True, "result_preview": "trend map"},
                    ],
                },
                {
                    "phase": "synthesis",
                    "success": True,
                    "tasks": [
                        {"subagent_type": "synthesizer", "success": True, "result_preview": "synth summary"},
                    ],
                },
            ],
        },
    }

    with patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(return_value=graph_result),
    ), patch(
        "src.task.handlers.workspace_feature_handler._persist_langgraph_artifacts",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.task.handlers.workspace_feature_handler._schedule_memory_extraction"
    ):
        result = await execute_workspace_feature(payload, progress)

    runtime = result.get("runtime")
    assert isinstance(runtime, dict)
    quality = result.get("quality")
    assert isinstance(quality, dict)
    assert quality.get("status") in {"pass", "warn"}
    blocks = {
        block.get("id"): block
        for block in runtime.get("blocks", [])
        if isinstance(block, dict) and isinstance(block.get("id"), str)
    }

    workflow_block = blocks.get("leader-workflow")
    assert isinstance(workflow_block, dict)
    assert workflow_block.get("phase_id") == "finalize"
    entries = workflow_block.get("entries")
    assert isinstance(entries, list)
    assert any(
        isinstance(item, dict)
        and item.get("label") == "策略"
        and item.get("value") == "deep_research:research_discovery"
        for item in entries
    )

    phases_block = blocks.get("leader-workflow-phases")
    assert isinstance(phases_block, dict)
    assert phases_block.get("phase_id") == "finalize"
    phase_items = phases_block.get("items")
    assert isinstance(phase_items, list)
    assert len(phase_items) == 2

    summary_block = blocks.get("result-summary")
    assert isinstance(summary_block, dict)
    assert summary_block.get("phase_id") == "finalize"
    summary_entries = summary_block.get("entries")
    assert isinstance(summary_entries, list)
    assert any(
        isinstance(item, dict)
        and item.get("label") == "Workflow"
        and item.get("value") == "completed"
        for item in summary_entries
    )
    assert "quality-gate" in blocks


@pytest.mark.asyncio
async def test_execute_workspace_feature_raises_when_quality_gate_fails() -> None:
    progress = AsyncMock()
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "thesis",
        "workspace_name": "Workspace Name",
        "workspace_description": "Workspace Description",
        "workspace_discipline": "computer_science",
        "feature_id": "deep_research",
        "execution_session_id": "exec-1",
        "params": {"topic": "Agent planning"},
    }

    with patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(return_value={"generation_mode": "llm"}),
    ), patch(
        "src.task.handlers.workspace_feature_handler._schedule_memory_extraction"
    ) as mock_schedule:
        with pytest.raises(RuntimeError, match="feature_quality_gate_failed"):
            await execute_workspace_feature(payload, progress)

    mock_schedule.assert_not_called()
