"""Tests for thesis_writing_service – outline and chapter payload builders."""

import pytest

from src.workspace_features.services.thesis_writing_service import (
    build_outline_payload,
    build_chapter_payload,
)


class TestBuildOutlinePayload:
    def test_returns_v1_schema(self):
        payload = build_outline_payload(
            paper_title="测试论文",
            target_words=20000,
            literature_count=12,
            deep_research_artifact_ids=["a1", "a2"],
        )
        assert payload["schema_version"] == "v1"
        assert payload["generation_mode"] in {"llm", "template_fallback"}
        assert payload["outline"]["chapters"]

    def test_paper_title_propagated(self):
        payload = build_outline_payload(
            paper_title="基于深度学习的文本分类",
            target_words=15000,
        )
        assert payload["paper_title"] == "基于深度学习的文本分类"

    def test_source_context_populated(self):
        payload = build_outline_payload(
            paper_title="测试",
            target_words=20000,
            literature_count=5,
            deep_research_artifact_ids=["dr-1"],
        )
        ctx = payload["source_context"]
        assert ctx["literature_count"] == 5
        assert ctx["deep_research_artifact_ids"] == ["dr-1"]

    def test_source_context_defaults(self):
        payload = build_outline_payload(
            paper_title="测试",
            target_words=20000,
        )
        ctx = payload["source_context"]
        assert ctx["literature_count"] == 0
        assert ctx["deep_research_artifact_ids"] == []

    def test_chapters_have_required_fields(self):
        payload = build_outline_payload(
            paper_title="测试",
            target_words=20000,
        )
        for chapter in payload["outline"]["chapters"]:
            assert "title" in chapter
            assert "position" in chapter
            assert "targetWords" in chapter
            assert isinstance(chapter["targetWords"], int)
            assert "keyPoints" in chapter
            assert "sections" in chapter


class TestBuildChapterPayload:
    def test_returns_v1_schema(self):
        payload = build_chapter_payload(
            paper_title="测试论文",
            chapter_index=0,
            chapter_title="绪论",
            target_words=2500,
        )
        assert payload["schema_version"] == "v1"
        assert payload["generation_mode"] in {"llm", "template_fallback"}
        assert payload["markdown"]

    def test_chapter_fields_propagated(self):
        payload = build_chapter_payload(
            paper_title="测试论文",
            chapter_index=2,
            chapter_title="方法与系统设计",
            target_words=5000,
        )
        assert payload["paper_title"] == "测试论文"
        assert payload["chapter_index"] == 2
        assert payload["chapter_title"] == "方法与系统设计"
        assert payload["target_words"] == 5000

    def test_estimated_words_present(self):
        payload = build_chapter_payload(
            paper_title="测试",
            chapter_index=0,
            chapter_title="绪论",
            target_words=3000,
        )
        assert "estimated_words" in payload
        assert isinstance(payload["estimated_words"], int)
        assert payload["estimated_words"] > 0

    def test_references_used_defaults_empty(self):
        payload = build_chapter_payload(
            paper_title="测试",
            chapter_index=0,
            chapter_title="绪论",
            target_words=2500,
        )
        assert payload["references_used"] == []

    def test_references_used_propagated(self):
        payload = build_chapter_payload(
            paper_title="测试",
            chapter_index=0,
            chapter_title="绪论",
            target_words=2500,
            references_used=["ref1", "ref2"],
        )
        assert payload["references_used"] == ["ref1", "ref2"]
