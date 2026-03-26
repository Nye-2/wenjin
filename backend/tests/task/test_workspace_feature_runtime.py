"""Runtime coverage tests for workspace feature handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.task.handlers.workspace_feature_handler import execute_workspace_feature


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
