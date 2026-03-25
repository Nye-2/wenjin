"""Tests for SCI workspace feature service helpers."""

from __future__ import annotations

import pytest

from src.workspace_features.services import sci_feature_service


@pytest.mark.asyncio
async def test_build_literature_search_payload_normalizes_query_and_tracks_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_load_workspace_literature(_workspace_id: str):
        return [{"title": "Paper A", "year": 2024, "venue": "ACL"}]

    async def _fake_try_llm_literature_search(**_kwargs):
        return (
            {
                "query": "研究主题",
                "discipline": "计算机科学",
                "papers": [{"title": "Paper A"}],
                "top_hits": [{"title": "Top Hit", "reason": "high relevance"}],
                "filters": {"sources": ["Semantic Scholar"]},
                "summary": "检索结果概述",
                "search_strategy": "llm_synthesis",
                "generated_at": "2026-03-25T00:00:00+00:00",
            },
            "sci-search-model",
            None,
        )

    monkeypatch.setattr(
        sci_feature_service,
        "_load_workspace_literature",
        _fake_load_workspace_literature,
    )
    monkeypatch.setattr(
        sci_feature_service,
        "_try_llm_literature_search",
        _fake_try_llm_literature_search,
    )

    payload = await sci_feature_service.build_literature_search_payload(
        workspace_id="ws-sci",
        query="",
        discipline="computer_science",
    )

    assert payload["query"] == "研究主题"
    assert payload["discipline"] == "计算机科学"
    assert payload["existing_literature_count"] == 1
    assert payload["model_id"] == "sci-search-model"
    assert payload["top_hits"][0]["title"] == "Top Hit"


@pytest.mark.asyncio
async def test_build_paper_analysis_payload_uses_fallback_title_and_returns_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_try_llm_paper_analysis(**_kwargs):
        return (
            {
                "paper_title": "未命名论文",
                "analysis_mode": "llm",
                "sections": {
                    "methodology": {
                        "title": "研究方法",
                        "content": "方法内容",
                        "key_points": ["要点"],
                    }
                },
                "summary": "整体评价",
                "quality_assessment": {"methodology_rigor": "高"},
                "recommendations": ["补充实验"],
                "generated_at": "2026-03-25T00:00:00+00:00",
            },
            "sci-analysis-model",
            None,
        )

    monkeypatch.setattr(
        sci_feature_service,
        "_try_llm_paper_analysis",
        _fake_try_llm_paper_analysis,
    )

    payload = await sci_feature_service.build_paper_analysis_payload(
        workspace_id="ws-sci",
        paper_title="",
        paper_abstract="摘要",
    )

    assert payload["paper_title"] == "未命名论文"
    assert payload["paper_id"] is None
    assert payload["model_id"] == "sci-analysis-model"
    assert payload["analysis_mode"] == "llm"
    assert payload["sections"]["methodology"]["title"] == "研究方法"
