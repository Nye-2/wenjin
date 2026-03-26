"""Tests for thesis writing graph helpers and action handlers."""

from __future__ import annotations

import pytest

from src.agents.graphs.thesis.thesis_writing import (
    _handle_review_section,
    _parse_json_response,
    _validate_review_result,
    thesis_writing_graph,
)


class TestParseJsonResponse:
    def test_valid_json(self):
        assert _parse_json_response('{"key":"value"}') == {"key": "value"}

    def test_fenced_json(self):
        assert _parse_json_response("```json\n{\"a\":1}\n```") == {"a": 1}

    def test_invalid_json(self):
        assert _parse_json_response("not json") is None


class TestValidateReviewResult:
    def test_valid(self):
        review = {
            "overall_score": 8.0,
            "issues": [],
            "strengths": ["清晰"],
            "revision_needed": False,
        }
        assert _validate_review_result(review) is True

    def test_invalid(self):
        assert _validate_review_result({"overall_score": "bad"}) is False


@pytest.mark.asyncio
async def test_generate_outline_action(monkeypatch: pytest.MonkeyPatch):
    async def _fake_build_outline_payload(**kwargs):
        _ = kwargs
        return {
            "paper_title": "测试论文",
            "outline": {"abstract": "摘要", "keywords": [], "chapters": [{"title": "绪论"}]},
            "schema_version": "v1",
            "source_context": {},
            "generation_mode": "llm",
            "model_id": "mock-model",
        }

    monkeypatch.setattr(
        "src.agents.graphs.thesis.thesis_writing.build_outline_payload",
        _fake_build_outline_payload,
    )
    monkeypatch.setattr(
        "src.agents.graphs.thesis.thesis_writing._resolve_writing_model",
        lambda _requested_model: "mock-model",
    )

    result = await thesis_writing_graph(
        initial_state={},
        payload={"params": {"action": "generate_outline", "paper_title": "测试论文"}},
    )
    assert result["action"] == "generate_outline"
    assert result["generation_mode"] == "llm"
    assert result["outline"]["chapters"]


@pytest.mark.asyncio
async def test_write_chapter_action(monkeypatch: pytest.MonkeyPatch):
    async def _fake_build_chapter_payload(**kwargs):
        _ = kwargs
        return {
            "paper_title": "测试论文",
            "chapter_index": 0,
            "chapter_title": "绪论",
            "target_words": 2500,
            "estimated_words": 2000,
            "markdown": "# 绪论\n\n正文",
            "references_used": [],
            "schema_version": "v1",
            "generation_mode": "llm",
            "model_id": "mock-model",
        }

    monkeypatch.setattr(
        "src.agents.graphs.thesis.thesis_writing.build_chapter_payload",
        _fake_build_chapter_payload,
    )
    monkeypatch.setattr(
        "src.agents.graphs.thesis.thesis_writing._resolve_writing_model",
        lambda _requested_model: "mock-model",
    )

    result = await thesis_writing_graph(
        initial_state={},
        payload={
            "params": {
                "action": "write_chapter",
                "paper_title": "测试论文",
                "chapter_title": "绪论",
            }
        },
    )
    assert result["action"] == "write_chapter"
    assert result["generation_mode"] == "llm"
    assert result["chapter"]["markdown"].startswith("#")


@pytest.mark.asyncio
async def test_review_section_raises_when_llm_invalid(monkeypatch: pytest.MonkeyPatch):
    async def _fake_review_section(*args, **kwargs):
        _ = args, kwargs
        return None

    monkeypatch.setattr(
        "src.agents.graphs.thesis.thesis_writing._review_section",
        _fake_review_section,
    )

    with pytest.raises(RuntimeError, match="review_section_llm_failed"):
        await _handle_review_section(
            params={"section_title": "绪论", "section_content": "内容"},
            memory_context=None,
            model_id="mock-model",
        )
