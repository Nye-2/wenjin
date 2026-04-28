"""Matrix coverage for the unified workspace feature task handler."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.task.handlers.workspace_feature_handler import execute_workspace_feature
from src.workspace_features import iter_workspace_features

FEATURE_HANDLER_MATRIX: list[tuple[str, str, dict[str, object], dict[str, object]]] = [
    ("thesis", "deep_research", {"topic": "Agent planning"}, {"topic": "Agent planning", "ideas": [], "gaps": []}),
    ("thesis", "literature_management", {"topic": "Agent planning"}, {"items": [], "summary": "inventory"}),
    (
        "thesis",
        "opening_research",
        {"topic": "Agent planning", "report_type": "opening_report"},
        {"report_type": "opening_report", "summary": "opening summary"},
    ),
    (
        "thesis",
        "thesis_writing",
        {"action": "generate_outline", "paper_title": "Agent Thesis"},
        {"action": "generate_outline", "paper_title": "Agent Thesis", "outline": {"chapters": [{"title": "绪论"}]}},
    ),
    ("thesis", "figure_generation", {"description": "系统架构图"}, {"description": "系统架构图"}),
    ("sci", "literature_search", {"query": "LLM planning"}, {"top_hits": [{"title": "Paper A"}], "papers": []}),
    (
        "sci",
        "paper_analysis",
        {"paper_title": "Paper A"},
        {"sections": {"methodology": {"title": "Methodology", "content": "content", "key_points": []}}},
    ),
    (
        "sci",
        "writing",
        {"paper_title": "Paper A", "section_type": "introduction"},
        {"section_type": "introduction", "section_title": "Introduction", "content": "Draft content", "references": []},
    ),
    ("sci", "literature_review", {"topic": "LLM planning"}, {"sections": [{"title": "Background", "content": "content"}]}),
    ("sci", "framework_outline", {"paper_title": "Paper A", "topic": "LLM planning"}, {"sections": [{"title": "Intro", "focus": "Background"}]}),
    ("sci", "peer_review", {"paper_title": "Paper A", "manuscript_excerpt": "Draft"}, {"weaknesses": ["Need more experiments"]}),
    ("sci", "journal_recommend", {"paper_title": "Paper A", "abstract": "Abstract"}, {"journals": [{"name": "Journal A", "fit": "high", "reason": "fit"}]}),
    ("proposal", "proposal_outline", {"topic": "智能体协同"}, {"sections": [{"title": "立项依据", "content": "内容"}]}),
    ("proposal", "background_research", {"keywords": "智能体协同"}, {"sections": [{"title": "现状综述", "content": "内容"}], "references": []}),
    ("proposal", "experiment_design", {"topic": "智能体协同", "objective": "验证协同效率"}, {"variables": [{"name": "x", "type": "independent"}]}),
    (
        "software_copyright",
        "copyright_materials",
        {"software_name": "Agent Studio", "version": "V2.0"},
        {"software_profile": {"software_name": "Agent Studio", "version": "V2.0"}},
    ),
    (
        "software_copyright",
        "technical_description",
        {"software_name": "Agent Studio"},
        {"sections": {"system_overview": {"title": "系统概述", "content": "内容"}}},
    ),
    (
        "patent",
        "patent_outline",
        {"innovation_description": "多智能体规划"},
        {"sections": [{"title": "技术领域", "content": "内容"}], "claims_draft": {"independent_claims": []}},
    ),
    (
        "patent",
        "prior_art_search",
        {"keywords": ["planning"], "ipc_codes": ["G06N3/04"]},
        {"comparison_table": [{"title": "Prior Art A"}], "novelty_risks": [], "avoidance_suggestions": []},
    ),
]


@pytest.fixture(autouse=True)
def _stub_feature_workflow_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_run_session(
        self: Any,  # noqa: ANN401
        request: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        from src.agents.harness import AgentSessionResult
        from src.subagents.parallel import PhaseResult

        phase_results: list[PhaseResult] = []
        for phase in request.phased_plan.phases:
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
            if callable(request.phase_callback):
                await request.phase_callback(phase_result)
            phase_results.append(phase_result)
        return AgentSessionResult(
            provider="test_harness",
            strategy=str(request.strategy),
            phase_results=phase_results,
        )

    monkeypatch.setattr(
        "src.agents.harness.native.NativeWenjinAgentHarness.run_session",
        _fake_run_session,
    )


def test_feature_handler_matrix_matches_registry() -> None:
    declared_feature_ids = {feature.id for feature in iter_workspace_features()}
    covered_feature_ids = {feature_id for _, feature_id, _, _ in FEATURE_HANDLER_MATRIX}

    assert covered_feature_ids == declared_feature_ids


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workspace_type", "feature_id", "params", "graph_result"),
    FEATURE_HANDLER_MATRIX,
)
async def test_execute_workspace_feature_wraps_langgraph_result_for_all_features(
    workspace_type: str,
    feature_id: str,
    params: dict[str, object],
    graph_result: dict[str, object],
) -> None:
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": workspace_type,
        "workspace_name": "Workspace Alpha",
        "workspace_description": "Workspace Description",
        "workspace_discipline": "computer_science",
        "feature_id": feature_id,
        "feature_name": feature_id,
        "handler_key": f"{workspace_type}.{feature_id}",
        "execution_session_id": "exec-1",
        "params": deepcopy(params),
        "user_id": "user-1",
    }
    progress = AsyncMock()
    persisted_artifacts = [{"id": "artifact-1", "type": "summary", "title": "Artifact Title"}]

    result_payload = deepcopy(graph_result)
    result_payload.setdefault("generation_mode", "llm")

    with patch(
        "src.agents.workspace_lead_agent.execute_feature_graph",
        new=AsyncMock(return_value=result_payload),
    ) as execute_feature_graph, patch(
        "src.task.handlers.workspace_feature_handler._persist_langgraph_artifacts",
        new=AsyncMock(return_value=persisted_artifacts),
    ) as persist_artifacts, patch(
        "src.task.handlers.workspace_feature_handler._schedule_memory_extraction"
    ) as schedule_memory:
        wrapped = await execute_workspace_feature(payload, progress)

    execute_feature_graph.assert_awaited_once()
    persist_artifacts.assert_awaited_once()
    schedule_memory.assert_called_once()

    assert wrapped["success"] is True
    assert wrapped["feature_id"] == feature_id
    assert wrapped["workspace_type"] == workspace_type
    assert wrapped["handler_key"] == f"{workspace_type}.{feature_id}"
    wrapped_data = wrapped["data"]
    assert isinstance(wrapped_data, dict)
    for key, value in result_payload.items():
        assert wrapped_data.get(key) == value
    extra_keys = set(wrapped_data) - set(result_payload)
    assert extra_keys.issubset({"leader_workflow"})
    assert wrapped["artifacts"] == persisted_artifacts
    assert wrapped["refresh_targets"] == ["artifacts"]
    assert isinstance(wrapped.get("runtime"), dict)
