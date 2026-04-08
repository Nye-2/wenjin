"""Tests for proposal workspace feature service helpers."""

from __future__ import annotations

import pytest

from src.artifacts import ArtifactType
from src.workspace_features.services import proposal_feature_service


@pytest.mark.asyncio
async def test_build_proposal_outline_payload_normalizes_topic_type_and_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_try_generate_proposal_sections(**_kwargs):
        return (
            [
                {"id": "basis", "title": "立项依据", "content": "内容", "source": "llm"},
                {"id": "objectives", "title": "研究目标与内容", "content": "内容", "source": "llm"},
                {"id": "methodology", "title": "研究方案与技术路线", "content": "内容", "source": "llm"},
                {"id": "schedule", "title": "计划进度", "content": "内容", "source": "llm"},
                {"id": "budget", "title": "经费预算框架", "content": "内容", "source": "llm"},
            ],
            "proposal-model",
            None,
        )

    monkeypatch.setattr(
        proposal_feature_service,
        "_try_generate_proposal_sections",
        _fake_try_generate_proposal_sections,
    )

    payload = await proposal_feature_service.build_proposal_outline_payload(
        workspace_id="ws-proposal",
        workspace_name="Proposal Workspace",
        topic="",
        proposal_type="国自然",
        period_months=0,
    )

    assert payload["topic"] == "Proposal Workspace"
    assert payload["proposal_type"] == "national_natural_science"
    assert payload["proposal_type_label"] == "国家自然科学基金"
    assert payload["period_months"] == 36
    assert payload["generation_mode"] == "llm"
    assert payload["model_id"] == "proposal-model"
    assert len(payload["sections"]) == 5


@pytest.mark.asyncio
async def test_build_background_research_payload_normalizes_scope_and_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_try_generate_background_sections(**_kwargs):
        return (
            [
                {"id": "overview", "title": "现状综述", "content": "综述内容", "source": "llm"},
                {"id": "problems", "title": "问题清单", "content": "问题内容", "source": "llm"},
                {"id": "directions", "title": "可行技术方向", "content": "方向内容", "source": "llm"},
            ],
            [
                {
                    "title": "Reference A",
                    "authors": "Author 1",
                    "year": "2024",
                    "venue": "Conference X",
                }
            ],
            "background-model",
            None,
        )

    monkeypatch.setattr(
        proposal_feature_service,
        "_try_generate_background_sections",
        _fake_try_generate_background_sections,
    )

    payload = await proposal_feature_service.build_background_research_payload(
        workspace_id="ws-proposal",
        workspace_name="研究任务",
        keywords="",
        industry_scope="",
        time_range="",
    )

    assert payload["schema_version"] == "v1"
    assert payload["output_language"] == proposal_feature_service.PROPOSAL_OUTPUT_LANGUAGE
    assert payload["keywords"] == "研究任务"
    assert payload["industry_scope"] == "相关领域"
    assert payload["time_range"] == "近5年"
    assert payload["model_id"] == "background-model"
    assert payload["references"][0]["title"] == "Reference A"


@pytest.mark.asyncio
async def test_build_experiment_design_payload_falls_back_to_template_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_try_llm_experiment_design(**_kwargs):
        return None, "experiment-model", "llm_output_not_json"

    monkeypatch.setattr(
        proposal_feature_service,
        "_try_llm_experiment_design",
        _fake_try_llm_experiment_design,
    )

    payload = await proposal_feature_service.build_experiment_design_payload(
        workspace_id="ws-proposal",
        workspace_name="实验设计任务",
        topic="多智能体系统",
        objective="提升协同规划效率",
    )

    assert payload["document_type"] == ArtifactType.METHODOLOGY.value
    assert payload["generation_mode"] == "template"
    assert payload["model_id"] == "experiment-model"
    assert payload["generation_error"] == "llm_output_not_json"
    assert payload["hypotheses"]
    assert payload["variables"]
