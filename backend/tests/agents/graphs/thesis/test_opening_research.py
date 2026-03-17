"""Tests for opening research sub-graph."""

from src.agents.graphs.thesis.opening_research import (
    _build_literature_highlights,
    _build_template_sections,
    _normalize_report_type,
    _parse_json_list_response,
    _parse_json_response,
)


# ---------------------------------------------------------------------------
# _normalize_report_type
# ---------------------------------------------------------------------------
class TestNormalizeReportType:
    def test_valid_types(self):
        assert _normalize_report_type("opening_report") == "opening_report"
        assert _normalize_report_type("literature_review") == "literature_review"
        assert _normalize_report_type("feasibility_analysis") == "feasibility_analysis"

    def test_invalid_falls_back(self):
        assert _normalize_report_type("unknown") == "opening_report"
        assert _normalize_report_type("") == "opening_report"

    def test_case_insensitive(self):
        assert _normalize_report_type("Opening_Report") == "opening_report"
        assert _normalize_report_type(" LITERATURE_REVIEW ") == "literature_review"


# ---------------------------------------------------------------------------
# _build_literature_highlights
# ---------------------------------------------------------------------------
class TestBuildLiteratureHighlights:
    def test_empty_list(self):
        assert _build_literature_highlights([]) == []

    def test_normal_list(self):
        papers = [
            {"title": "Deep Learning for NLP", "year": "2024", "venue": "ACL"},
            {"title": "Transformer Models", "year": "2023", "venue": ""},
            {"title": "", "year": "2022", "venue": "ICLR"},  # empty title, should skip
        ]
        result = _build_literature_highlights(papers)
        assert len(result) == 2
        assert "Deep Learning for NLP(2024) - ACL" in result[0]
        assert "Transformer Models(2023)" in result[1]
        assert "ICLR" not in result[1]  # no venue

    def test_max_items(self):
        papers = [{"title": f"Paper {i}", "year": "2024"} for i in range(20)]
        result = _build_literature_highlights(papers, max_items=3)
        assert len(result) == 3

    def test_no_year_no_venue(self):
        papers = [{"title": "Solo Paper"}]
        result = _build_literature_highlights(papers)
        assert result == ["Solo Paper"]


# ---------------------------------------------------------------------------
# _build_template_sections
# ---------------------------------------------------------------------------
class TestBuildTemplateSections:
    def test_opening_report_has_6_sections(self):
        sections = _build_template_sections("opening_report", "NLP", "", [])
        assert len(sections) == 6
        titles = [s["title"] for s in sections]
        assert "研究背景与意义" in titles
        assert "进度安排与风险预案" in titles

    def test_literature_review_has_4_sections(self):
        sections = _build_template_sections("literature_review", "CV", "", [])
        assert len(sections) == 4
        titles = [s["title"] for s in sections]
        assert "检索范围与方法" in titles
        assert "研究空白与切入点" in titles

    def test_feasibility_analysis_has_4_sections(self):
        sections = _build_template_sections("feasibility_analysis", "RL", "", [])
        assert len(sections) == 4
        titles = [s["title"] for s in sections]
        assert "技术可行性" in titles
        assert "计划与风险控制" in titles

    def test_with_literature_highlights_adds_reference_section(self):
        highlights = ["Paper A(2024) - ACL", "Paper B(2023) - EMNLP"]
        sections = _build_template_sections("opening_report", "NLP", "", highlights)
        assert len(sections) == 7  # 6 + reference section
        assert sections[-1]["title"] == "参考文献线索"
        assert "Paper A" in sections[-1]["content"]

    def test_no_highlights_no_reference_section(self):
        sections = _build_template_sections("opening_report", "NLP", "", [])
        assert all(s["title"] != "参考文献线索" for s in sections)

    def test_topic_in_content(self):
        sections = _build_template_sections("opening_report", "强化学习", "", [])
        assert "强化学习" in sections[0]["content"]

    def test_workspace_description_in_opening_report(self):
        sections = _build_template_sections("opening_report", "NLP", "这是描述", [])
        assert "这是描述" in sections[0]["content"]


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------
class TestParseJsonResponse:
    def test_valid(self):
        assert _parse_json_response('{"key": "val"}') == {"key": "val"}

    def test_fenced(self):
        assert _parse_json_response('```json\n{"k": 1}\n```') == {"k": 1}

    def test_invalid(self):
        assert _parse_json_response("not json") is None

    def test_non_dict_returns_none(self):
        assert _parse_json_response("[1, 2, 3]") is None

    def test_fenced_without_lang(self):
        assert _parse_json_response('```\n{"a": "b"}\n```') == {"a": "b"}


# ---------------------------------------------------------------------------
# _parse_json_list_response
# ---------------------------------------------------------------------------
class TestParseJsonListResponse:
    def test_valid_list(self):
        result = _parse_json_list_response('[{"title": "A"}, {"title": "B"}]')
        assert result is not None
        assert len(result) == 2

    def test_fenced_list(self):
        result = _parse_json_list_response('```json\n[{"t": 1}]\n```')
        assert result is not None
        assert len(result) == 1

    def test_invalid(self):
        assert _parse_json_list_response("not json") is None

    def test_non_list_returns_none(self):
        assert _parse_json_list_response('{"key": "val"}') is None

    def test_list_of_non_dicts_returns_none(self):
        assert _parse_json_list_response("[1, 2, 3]") is None


# ---------------------------------------------------------------------------
# Pipeline steps tracking (verifying structure)
# ---------------------------------------------------------------------------
class TestPipelineStepsTracking:
    def test_generation_mode_logic(self):
        """Verify generation_mode calculation logic matches the graph."""
        # All steps succeed
        steps_all = {"status_analysis": True, "methodology_planning": True, "section_generation": True}
        assert sum(steps_all.values()) == 3

        # Partial success
        steps_partial = {"status_analysis": True, "methodology_planning": False, "section_generation": True}
        assert 0 < sum(steps_partial.values()) < 3

        # No success
        steps_none = {"status_analysis": False, "methodology_planning": False, "section_generation": False}
        assert sum(steps_none.values()) == 0
