"""Tests for thesis_writing_service."""

import pytest

from src.workspace_features.services.thesis_writing_service import (
    build_chapter_payload,
    build_outline_payload,
)


@pytest.mark.asyncio
async def test_build_outline_payload_success(monkeypatch: pytest.MonkeyPatch):
    async def _fake_load_deep_research_snapshot(**kwargs):
        _ = kwargs
        return {
            "artifact_ids": [],
            "idea_items": [],
            "gap_highlights": [],
        }

    async def _fake_invoke_json_llm(**kwargs):
        _ = kwargs
        return (
            {
                "abstract": "摘要",
                "keywords": ["关键词1", "关键词2"],
                "chapters": [
                    {
                        "title": "绪论",
                        "position": "研究背景",
                        "targetWords": 3000,
                        "keyPoints": ["问题定义", "研究目标"],
                        "sections": ["1.1 背景", "1.2 问题"],
                    }
                ],
            },
            "model-a",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.thesis_writing_service._load_deep_research_snapshot",
        _fake_load_deep_research_snapshot,
    )
    monkeypatch.setattr(
        "src.workspace_features.services.thesis_writing_service._invoke_json_llm",
        _fake_invoke_json_llm,
    )

    payload = await build_outline_payload(
        paper_title="测试论文",
        target_words=20000,
        literature_count=12,
        deep_research_artifact_ids=["a1", "a2"],
    )

    assert payload["schema_version"] == "v1"
    assert payload["generation_mode"] == "llm"
    assert payload["model_id"] == "model-a"
    assert payload["outline"]["chapters"]


@pytest.mark.asyncio
async def test_build_outline_payload_raises_on_llm_failure(monkeypatch: pytest.MonkeyPatch):
    async def _fake_load_deep_research_snapshot(**kwargs):
        _ = kwargs
        return {
            "artifact_ids": [],
            "idea_items": [],
            "gap_highlights": [],
        }

    async def _fake_invoke_json_llm(**kwargs):
        _ = kwargs
        return None, "model-a", "llm_output_not_json"

    monkeypatch.setattr(
        "src.workspace_features.services.thesis_writing_service._load_deep_research_snapshot",
        _fake_load_deep_research_snapshot,
    )
    monkeypatch.setattr(
        "src.workspace_features.services.thesis_writing_service._invoke_json_llm",
        _fake_invoke_json_llm,
    )

    with pytest.raises(RuntimeError, match="outline_generation_failed"):
        await build_outline_payload(paper_title="测试论文")


@pytest.mark.asyncio
async def test_build_outline_payload_includes_deep_research_context(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_load_deep_research_snapshot(**kwargs):
        _ = kwargs
        return {
            "artifact_ids": ["dr-1"],
            "idea_items": [
                {"title": "跨域泛化方法", "description": "融合迁移学习与对比学习"},
            ],
            "gap_highlights": ["数据集泛化不足"],
        }

    async def _fake_invoke_json_llm(**kwargs):
        _ = kwargs
        return (
            {
                "abstract": "摘要",
                "keywords": ["关键词1", "关键词2"],
                "chapters": [
                    {
                        "title": "绪论",
                        "position": "研究背景",
                        "targetWords": 3000,
                        "keyPoints": ["问题定义", "研究目标"],
                        "sections": ["1.1 背景", "1.2 问题"],
                    }
                ],
            },
            "model-a",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.thesis_writing_service._load_deep_research_snapshot",
        _fake_load_deep_research_snapshot,
    )
    monkeypatch.setattr(
        "src.workspace_features.services.thesis_writing_service._invoke_json_llm",
        _fake_invoke_json_llm,
    )

    payload = await build_outline_payload(
        paper_title="测试论文",
        workspace_id="ws-1",
        deep_research_artifact_ids=["dr-1"],
    )

    source_context = payload["source_context"]
    assert source_context["deep_research_artifact_ids"] == ["dr-1"]
    assert source_context["deep_research_idea_titles"] == ["跨域泛化方法"]
    assert source_context["deep_research_gap_highlights"] == ["数据集泛化不足"]


@pytest.mark.asyncio
async def test_build_chapter_payload_success(monkeypatch: pytest.MonkeyPatch):
    async def _fake_invoke_json_llm(**kwargs):
        _ = kwargs
        return (
            {
                "markdown": "# 绪论\n\n## 研究背景\n内容",
                "estimated_words": 2100,
                "references_used": ["ref1", "ref2"],
            },
            "model-b",
            None,
        )

    monkeypatch.setattr(
        "src.workspace_features.services.thesis_writing_service._invoke_json_llm",
        _fake_invoke_json_llm,
    )

    payload = await build_chapter_payload(
        paper_title="测试论文",
        chapter_index=0,
        chapter_title="绪论",
        target_words=2500,
        references_used=["input-ref"],
    )

    assert payload["schema_version"] == "v1"
    assert payload["generation_mode"] == "llm"
    assert payload["model_id"] == "model-b"
    assert payload["markdown"].startswith("#")
    assert payload["references_used"] == ["ref1", "ref2"]


@pytest.mark.asyncio
async def test_build_chapter_payload_raises_on_llm_failure(monkeypatch: pytest.MonkeyPatch):
    async def _fake_invoke_json_llm(**kwargs):
        _ = kwargs
        return None, "model-b", "llm_output_not_json"

    monkeypatch.setattr(
        "src.workspace_features.services.thesis_writing_service._invoke_json_llm",
        _fake_invoke_json_llm,
    )

    with pytest.raises(RuntimeError, match="chapter_generation_failed"):
        await build_chapter_payload(
            paper_title="测试论文",
            chapter_index=0,
            chapter_title="绪论",
        )
