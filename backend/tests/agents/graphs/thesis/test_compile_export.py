"""Tests for compile export sub-graph — pure function tests only."""

from types import SimpleNamespace

import pytest

from src.agents.graphs.thesis.compile_export import (
    _determine_generation_mode,
    _extract_chapter_summaries,
    _parse_json_response,
)


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------
class TestParseJsonResponse:
    def test_valid(self):
        assert _parse_json_response('{"key": "val"}') == {"key": "val"}

    def test_fenced(self):
        assert _parse_json_response('```json\n{"k": 1}\n```') == {"k": 1}

    def test_fenced_without_lang(self):
        assert _parse_json_response('```\n{"a": "b"}\n```') == {"a": "b"}

    def test_invalid(self):
        assert _parse_json_response("not json") is None

    def test_non_dict_returns_none(self):
        assert _parse_json_response("[1, 2, 3]") is None

    def test_empty_string(self):
        assert _parse_json_response("") is None

    def test_nested_json(self):
        result = _parse_json_response('{"a": {"b": [1, 2]}}')
        assert result == {"a": {"b": [1, 2]}}

    def test_whitespace_wrapped(self):
        result = _parse_json_response('  \n{"ok": true}\n  ')
        assert result == {"ok": True}


# ---------------------------------------------------------------------------
# _extract_chapter_summaries
# ---------------------------------------------------------------------------
class TestExtractChapterSummaries:
    def test_empty_list(self):
        assert _extract_chapter_summaries([]) == []

    def test_no_chapter_artifacts(self):
        artifacts = [
            {"type": "framework_outline", "title": "outline", "content": {}},
            {"type": "figure", "title": "fig1", "content": {}},
        ]
        assert _extract_chapter_summaries(artifacts) == []

    def test_extracts_chapters(self):
        artifacts = [
            {
                "type": "thesis_chapter",
                "title": "Ch1",
                "content": {
                    "chapter_title": "Introduction",
                    "chapter_index": 1,
                    "markdown": "This is the introduction chapter.",
                },
            },
            {
                "type": "thesis_chapter",
                "title": "Ch2",
                "content": {
                    "chapter_title": "Methods",
                    "chapter_index": 2,
                    "markdown": "This chapter describes the methodology.",
                },
            },
            {
                "type": "framework_outline",
                "title": "Outline",
                "content": {},
            },
        ]
        result = _extract_chapter_summaries(artifacts)
        assert len(result) == 2
        assert result[0]["title"] == "Introduction"
        assert result[1]["title"] == "Methods"
        assert "introduction" in result[0]["summary"].lower()
        assert "methodology" in result[1]["summary"].lower()

    def test_sorts_by_chapter_index(self):
        artifacts = [
            {
                "type": "thesis_chapter",
                "title": "Ch3",
                "content": {
                    "chapter_title": "Conclusion",
                    "chapter_index": 3,
                    "markdown": "Conclusion text.",
                },
            },
            {
                "type": "thesis_chapter",
                "title": "Ch1",
                "content": {
                    "chapter_title": "Introduction",
                    "chapter_index": 1,
                    "markdown": "Intro text.",
                },
            },
        ]
        result = _extract_chapter_summaries(artifacts)
        assert result[0]["title"] == "Introduction"
        assert result[1]["title"] == "Conclusion"

    def test_truncation(self):
        long_text = "A" * 1000
        artifacts = [
            {
                "type": "thesis_chapter",
                "title": "Ch1",
                "content": {
                    "chapter_title": "Long Chapter",
                    "chapter_index": 1,
                    "markdown": long_text,
                },
            },
        ]
        result = _extract_chapter_summaries(artifacts, max_content_chars=500)
        assert len(result) == 1
        assert len(result[0]["summary"]) == 500

    def test_custom_truncation_length(self):
        text = "B" * 200
        artifacts = [
            {
                "type": "thesis_chapter",
                "title": "Ch1",
                "content": {
                    "chapter_title": "Short Chapter",
                    "chapter_index": 1,
                    "markdown": text,
                },
            },
        ]
        result = _extract_chapter_summaries(artifacts, max_content_chars=100)
        assert len(result[0]["summary"]) == 100

    def test_missing_chapter_index_sorts_last(self):
        artifacts = [
            {
                "type": "thesis_chapter",
                "title": "NoIndex",
                "content": {
                    "chapter_title": "No Index Chapter",
                    "markdown": "No index.",
                },
            },
            {
                "type": "thesis_chapter",
                "title": "Ch1",
                "content": {
                    "chapter_title": "Indexed Chapter",
                    "chapter_index": 1,
                    "markdown": "Indexed.",
                },
            },
        ]
        result = _extract_chapter_summaries(artifacts)
        assert result[0]["title"] == "Indexed Chapter"
        assert result[1]["title"] == "No Index Chapter"

    def test_falls_back_to_artifact_title(self):
        artifacts = [
            {
                "type": "thesis_chapter",
                "title": "Fallback Title",
                "content": {
                    "chapter_index": 1,
                    "markdown": "Some text.",
                },
            },
        ]
        result = _extract_chapter_summaries(artifacts)
        assert result[0]["title"] == "Fallback Title"

    def test_empty_markdown(self):
        artifacts = [
            {
                "type": "thesis_chapter",
                "title": "Ch1",
                "content": {
                    "chapter_title": "Empty",
                    "chapter_index": 1,
                    "markdown": "",
                },
            },
        ]
        result = _extract_chapter_summaries(artifacts)
        assert result[0]["summary"] == ""

    def test_missing_content_key(self):
        artifacts = [
            {
                "type": "thesis_chapter",
                "title": "Ch1",
                "content": None,
            },
        ]
        result = _extract_chapter_summaries(artifacts)
        # content is None -> not a dict -> skip
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _determine_generation_mode
# ---------------------------------------------------------------------------
class TestDetermineGenerationMode:
    def test_both_succeed(self):
        assert _determine_generation_mode(True, True) == "llm"

    def test_only_consistency(self):
        assert _determine_generation_mode(True, False) == "partial_llm"

    def test_only_abstract(self):
        assert _determine_generation_mode(False, True) == "partial_llm"

    def test_neither_succeed(self):
        assert _determine_generation_mode(False, False) == "failed"


# ---------------------------------------------------------------------------
# Pipeline steps logic
# ---------------------------------------------------------------------------
class TestPipelineStepsLogic:
    """Verify the pipeline_steps dict construction mirrors generation_mode."""

    def test_all_true_means_llm(self):
        steps = {"consistency_review": True, "abstract_generation": True}
        mode = _determine_generation_mode(
            steps["consistency_review"], steps["abstract_generation"],
        )
        assert mode == "llm"

    def test_mixed_means_partial(self):
        steps = {"consistency_review": True, "abstract_generation": False}
        mode = _determine_generation_mode(
            steps["consistency_review"], steps["abstract_generation"],
        )
        assert mode == "partial_llm"

    def test_all_false_means_failed(self):
        steps = {"consistency_review": False, "abstract_generation": False}
        mode = _determine_generation_mode(
            steps["consistency_review"], steps["abstract_generation"],
        )
        assert mode == "failed"


@pytest.mark.asyncio
async def test_compile_export_graph_passes_llm_abstract_to_compile_payload(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.agents.graphs.thesis import compile_export

    async def _fake_load_outline_context(_workspace_id: str):
        return {"paper_title": "测试论文"}

    async def _fake_load_chapter_summaries(_workspace_id: str):
        return [{"title": "绪论", "summary": "章节摘要"}]

    async def _fake_load_literature_count(_workspace_id: str):
        return 12

    async def _fake_review_consistency(**kwargs):
        return {"issues": [], "overall_assessment": "ok"}

    async def _fake_generate_abstract_keywords(**kwargs):
        return {
            "abstract_zh": "覆盖摘要",
            "keywords_zh": ["关键词1", "关键词2"],
            "abstract_en": "Abstract",
            "keywords_en": ["kw1", "kw2"],
        }

    captured: dict[str, object] = {}

    async def _fake_build_compile_payload(**kwargs):
        captured.update(kwargs)
        return {
            "latex_content": "latex",
            "bib_content": "",
            "source_summary": {"chapter_count": 1, "literature_count": 12},
            "template": "default",
            "compiler": "xelatex",
            "bibliography_style": "gbt7714",
            "paper_title": "测试论文",
            "keywords": ["关键词1", "关键词2"],
            "abstract_source": "llm_override",
        }

    async def _fake_compile_thesis_payload(**kwargs):
        captured["compile_kwargs"] = kwargs
        return SimpleNamespace(
            latex_project_id="latex-thesis-1",
            main_file="main.tex",
            compile_status="success",
            pdf_path="/mnt/user-data/execution/latex_compile/test/main.pdf",
            pdf_url="/api/threads/thread-1/artifacts/mnt/user-data/execution/latex_compile/test/main.pdf",
            pdf_endpoint="/api/threads/thread-1/artifacts/mnt/user-data/execution/latex_compile/test/main.pdf",
            page_count=8,
            compile_error=None,
            compile_logs="ok",
            sync_conflicts=[],
        )

    monkeypatch.setattr(
        compile_export,
        "_load_outline_context",
        _fake_load_outline_context,
    )
    monkeypatch.setattr(
        compile_export,
        "_load_chapter_summaries",
        _fake_load_chapter_summaries,
    )
    monkeypatch.setattr(
        compile_export,
        "_load_literature_count",
        _fake_load_literature_count,
    )
    monkeypatch.setattr(
        compile_export,
        "_review_consistency",
        _fake_review_consistency,
    )
    monkeypatch.setattr(
        compile_export,
        "_generate_abstract_keywords",
        _fake_generate_abstract_keywords,
    )
    monkeypatch.setattr(
        compile_export,
        "_resolve_writing_model",
        lambda _requested_model: "mock-model",
    )
    monkeypatch.setattr(
        compile_export,
        "build_compile_payload",
        _fake_build_compile_payload,
    )
    monkeypatch.setattr(
        compile_export,
        "compile_thesis_payload",
        _fake_compile_thesis_payload,
    )

    result = await compile_export.compile_export_graph(
        initial_state={},
        payload={
            "workspace_id": "ws-1",
            "workspace_name": "测试论文",
            "workspace_description": "描述",
            "thread_id": "thread-1",
            "params": {
                "template": "default",
                "compiler": "xelatex",
                "bibliography_style": "gbt7714",
            },
        },
    )

    assert captured.get("abstract_override") == "覆盖摘要"
    assert captured.get("keywords_override") == ["关键词1", "关键词2"]
    assert captured["compile_kwargs"]["workspace_id"] == "ws-1"
    assert result["keywords"] == ["关键词1", "关键词2"]
    assert result["abstract_source"] == "llm_override"
    assert result["latex_project_id"] == "latex-thesis-1"
    assert result["compile_status"] == "success"


@pytest.mark.asyncio
async def test_compile_export_graph_uses_outline_title_for_abstract_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.agents.graphs.thesis import compile_export

    captured: dict[str, object] = {}

    async def _fake_load_outline_context(_workspace_id: str):
        return {"paper_title": "真正论文标题"}

    async def _fake_load_chapter_summaries(_workspace_id: str):
        return [{"title": "绪论", "summary": "章节摘要"}]

    async def _fake_load_literature_count(_workspace_id: str):
        return 3

    async def _fake_review_consistency(**_kwargs):
        return {"issues": [], "overall_assessment": "ok"}

    async def _fake_generate_abstract_keywords(**kwargs):
        captured["topic"] = kwargs.get("topic")
        return {
            "abstract_zh": "覆盖摘要",
            "keywords_zh": ["关键词1"],
            "abstract_en": "Abstract",
            "keywords_en": ["kw1"],
        }

    async def _fake_build_compile_payload(**_kwargs):
        return {
            "latex_content": "latex",
            "bib_content": "",
            "source_summary": {"chapter_count": 1, "literature_count": 3},
            "template": "default",
            "compiler": "xelatex",
            "bibliography_style": "gbt7714",
            "paper_title": "真正论文标题",
            "keywords": ["关键词1"],
            "abstract_source": "llm_override",
        }

    async def _fake_compile_thesis_payload(**_kwargs):
        return SimpleNamespace(
            latex_project_id="latex-thesis-1",
            main_file="main.tex",
            compile_status="success",
            pdf_path="/mnt/user-data/execution/latex_compile/test/main.pdf",
            pdf_url="/api/threads/thread-1/artifacts/mnt/user-data/execution/latex_compile/test/main.pdf",
            pdf_endpoint="/api/threads/thread-1/artifacts/mnt/user-data/execution/latex_compile/test/main.pdf",
            page_count=8,
            compile_error=None,
            compile_logs="ok",
            sync_conflicts=[],
        )

    monkeypatch.setattr(compile_export, "_load_outline_context", _fake_load_outline_context)
    monkeypatch.setattr(compile_export, "_load_chapter_summaries", _fake_load_chapter_summaries)
    monkeypatch.setattr(compile_export, "_load_literature_count", _fake_load_literature_count)
    monkeypatch.setattr(compile_export, "_review_consistency", _fake_review_consistency)
    monkeypatch.setattr(compile_export, "_generate_abstract_keywords", _fake_generate_abstract_keywords)
    monkeypatch.setattr(compile_export, "_resolve_writing_model", lambda _requested_model: "mock-model")
    monkeypatch.setattr(compile_export, "build_compile_payload", _fake_build_compile_payload)
    monkeypatch.setattr(compile_export, "compile_thesis_payload", _fake_compile_thesis_payload)

    result = await compile_export.compile_export_graph(
        initial_state={},
        payload={
            "workspace_id": "ws-1",
            "workspace_name": "工作区标题",
            "workspace_description": "描述",
            "params": {},
        },
    )

    assert captured["topic"] == "真正论文标题"
    assert result["paper_title"] == "真正论文标题"
