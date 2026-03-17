"""Tests for literature management sub-graph."""

from src.agents.graphs.thesis.literature_management import (
    _build_recommendations,
    _compute_statistics,
    _parse_json_response,
)


class TestComputeStatistics:
    def test_empty_literature(self):
        result = _compute_statistics([], "NLP")
        assert result["summary"]["total"] == 0

    def test_with_papers(self):
        papers = [
            {"title": "Paper A", "citations": 50, "year": "2024", "source": "Scopus", "abstract": "abc", "doi": "10.1"},
            {"title": "Paper B", "citations": 5, "year": "2023", "source": "Scopus", "abstract": None, "doi": None},
        ]
        result = _compute_statistics(papers, "NLP")
        assert result["summary"]["total"] == 2
        assert result["summary"]["core_count"] == 1
        assert result["quality_check"]["missing_abstract"] == 1
        assert result["quality_check"]["missing_doi"] == 1

    def test_top_cited_sorted(self):
        papers = [
            {"title": "Low", "citations": 1, "year": "2024"},
            {"title": "High", "citations": 100, "year": "2024"},
        ]
        result = _compute_statistics(papers, "test")
        assert result["top_cited"][0]["title"] == "High"


class TestBuildRecommendations:
    def test_low_count(self):
        recs = _build_recommendations(5, 0, 0, 3)
        assert any("15" in r for r in recs)

    def test_all_good(self):
        recs = _build_recommendations(20, 0, 0, 5)
        assert recs == ["文献库质量良好"]


class TestParseJsonResponse:
    def test_valid(self):
        assert _parse_json_response('{"key": "val"}') == {"key": "val"}

    def test_fenced(self):
        assert _parse_json_response('```json\n{"k": 1}\n```') == {"k": 1}

    def test_invalid(self):
        assert _parse_json_response("not json") is None
