"""Tests for compile export sub-graph — pure function tests only."""

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
        assert _determine_generation_mode(False, False) == "template_fallback"


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

    def test_all_false_means_fallback(self):
        steps = {"consistency_review": False, "abstract_generation": False}
        mode = _determine_generation_mode(
            steps["consistency_review"], steps["abstract_generation"],
        )
        assert mode == "template_fallback"
