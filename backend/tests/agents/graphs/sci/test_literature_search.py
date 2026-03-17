"""Tests for SCI literature search sub-graph."""

from src.agents.graphs.sci.literature_search import (
    _build_literature_search_template,
    _build_paper_search_result,
    _extract_literature_search_params,
)


class TestExtractLiteratureSearchParams:
    def test_empty_params(self):
        result = _extract_literature_search_params({}, "Test Workspace", None)
        assert result["query"] == "Test Workspace"
        assert result["discipline"] == "综合"
        assert result["preferred_model"] is None

        assert result["existing_literature"] == []
    def test_with_query(self):
        params = {"query": "machine learning", "model_id": "gpt-4"}
        result = _extract_literature_search_params(params, "Workspace", None)
        assert result["query"] == "machine learning"
        assert result["preferred_model"] == "gpt-4"
        assert result["discipline"] == "综合"
    def test_with_discipline(self):
        params = {"discipline": "计算机科学"}
        result = _extract_literature_search_params(params, "Workspace", None)
        assert result["discipline"] == "计算机科学"


class TestBuildPaperSearchResult:
    def test_basic_result(self):
        paper = _build_paper_search_result(
            {"title": "Test Paper", "year": "2024", "citations": 10},
            "NLP",
            "Computer Science",
        )
        assert paper["title"] == "Test Paper"
        assert paper["year"] == "2024"
        assert paper["relevance"] == "10"
        assert paper["source"] == "Manual"
    def test_missing_fields(self):
        paper = _build_paper_search_result({}, "Test", "Field")
        assert paper["title"] == "Test"
        assert paper["year"] == "2024"
        assert paper["relevance"] == "0"
class TestBuildLiteratureSearchTemplate:
    def test_basic_template(self):
        template = _build_literature_search_template("machine learning", "Computer Science")
        assert template["query"] == "machine learning"
        assert template["discipline"] == "Computer Science"
        assert template["search_strategy"] == "template_fallback"
        assert "papers" in template
