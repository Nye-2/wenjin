"""Tests for patent workspace feature service helpers."""

from __future__ import annotations

import pytest

from src.workspace_features.services import patent_feature_service


@pytest.mark.asyncio
async def test_build_patent_outline_payload_uses_workspace_fallback_and_marks_llm_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_try_generate_patent_outline_llm(**_kwargs):
        return (
            {
                "sections": [
                    {"id": "technical_field", "title": "技术领域", "content": "领域描述"},
                    {"id": "background_art", "title": "背景技术", "content": "背景描述"},
                ],
                "claims_draft": {
                    "independent_claims": [
                        {"id": "claim_1", "type": "独立权利要求", "content": "权利要求内容"}
                    ],
                    "dependent_claims": [
                        {"id": "claim_2", "type": "从属权利要求", "content": "从属内容"}
                    ],
                    "hints": ["提示"],
                },
            },
            "patent-model",
            None,
        )

    monkeypatch.setattr(
        patent_feature_service,
        "_try_generate_patent_outline_llm",
        _fake_try_generate_patent_outline_llm,
    )

    payload = await patent_feature_service.build_patent_outline_payload(
        workspace_id="ws-patent",
        workspace_name="专利任务",
        workspace_description="一种多模态规划系统",
        innovation_description="",
        technical_field="人工智能",
        application_scenario="工业优化",
        implementation_method="规则 + 模型混合推理",
    )

    assert payload["innovation_description"] == "一种多模态规划系统"
    assert payload["model_id"] == "patent-model"
    assert payload["generation_mode"] == "llm"
    assert payload["sections"][0]["source"] == "llm"
    assert payload["claims_draft"]["independent_claims"][0]["source"] == "llm"
    assert payload["claims_draft"]["dependent_claims"][0]["source"] == "llm"
    assert payload["evidence_points_needed"]


@pytest.mark.asyncio
async def test_build_prior_art_search_payload_normalizes_string_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_try_generate_prior_art_llm(**_kwargs):
        return (
            {
                "search_scope": {"keywords": ["should", "be", "overridden"]},
                "comparison_table": [
                    {
                        "id": "ref-1",
                        "title": "Prior Art A",
                        "patent_number": "CN123",
                        "comparison": {"novelty_assessment": "medium"},
                    }
                ],
                "novelty_risks": [
                    {"id": "risk-1", "level": "high", "description": "冲突点", "mitigation": "规避建议"}
                ],
                "avoidance_suggestions": [
                    {"id": "s-1", "category": "claim", "content": "缩小权利要求范围"}
                ],
            },
            "prior-art-model",
            None,
        )

    monkeypatch.setattr(
        patent_feature_service,
        "_try_generate_prior_art_llm",
        _fake_try_generate_prior_art_llm,
    )

    payload = await patent_feature_service.build_prior_art_search_payload(
        workspace_id="ws-patent",
        workspace_name="Patent Workspace",
        workspace_description="边缘计算推理框架",
        keywords=" transformer , planning ",
        ipc_codes=" g06f17/27 , g06n3/04 ",
        time_range="",
    )

    assert payload["keywords"] == ["transformer", "planning"]
    assert payload["ipc_codes"] == ["G06F17/27", "G06N3/04"]
    assert payload["time_range"] == "近5年"
    assert payload["search_scope"]["keywords"] == ["transformer", "planning"]
    assert payload["search_scope"]["ipc_codes"] == ["G06F17/27", "G06N3/04"]
    assert payload["model_id"] == "prior-art-model"
    assert payload["next_steps"]
