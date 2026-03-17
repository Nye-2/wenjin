"""Tests for deep research sub-graph."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.graphs.thesis.deep_research import (
    _build_discovery_summary,
    _determine_generation_mode,
    _parse_json_list_response,
    _parse_json_response,
    _phase1_discovery,
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

    def test_nested_dict(self):
        result = _parse_json_response('{"a": {"b": 1}, "c": [1, 2]}')
        assert result == {"a": {"b": 1}, "c": [1, 2]}


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

    def test_empty_list(self):
        result = _parse_json_list_response("[]")
        assert result is not None
        assert len(result) == 0

    def test_mixed_list_returns_none(self):
        assert _parse_json_list_response('[{"a": 1}, 2]') is None


# ---------------------------------------------------------------------------
# _build_discovery_summary
# ---------------------------------------------------------------------------
class TestBuildDiscoverySummary:
    def test_empty_discovery(self):
        result = _build_discovery_summary({})
        assert result == "（暂无发现结果）"

    def test_empty_lists(self):
        discovery = {"seminal_works": [], "recent_works": [], "trends": []}
        result = _build_discovery_summary(discovery)
        assert result == "（暂无发现结果）"

    def test_with_seminal_works(self):
        discovery = {
            "seminal_works": [
                {"title": "Attention Is All You Need", "year": 2017, "significance": "Introduced transformer architecture"},
            ],
            "recent_works": [],
            "trends": [],
        }
        result = _build_discovery_summary(discovery)
        assert "经典文献:" in result
        assert "Attention Is All You Need" in result
        assert "2017" in result
        assert "Introduced transformer" in result

    def test_with_recent_works(self):
        discovery = {
            "seminal_works": [],
            "recent_works": [
                {"title": "GPT-4 Technical Report", "year": 2023, "significance": "State-of-the-art LLM"},
            ],
            "trends": [],
        }
        result = _build_discovery_summary(discovery)
        assert "近期文献:" in result
        assert "GPT-4" in result

    def test_with_trends(self):
        discovery = {
            "seminal_works": [],
            "recent_works": [],
            "trends": [
                {"topic": "多模态学习", "description": "结合视觉与语言的模型"},
            ],
        }
        result = _build_discovery_summary(discovery)
        assert "研究趋势:" in result
        assert "多模态学习" in result

    def test_with_all_sections(self):
        discovery = {
            "seminal_works": [{"title": "Paper A", "year": 2020, "significance": "Sig A"}],
            "recent_works": [{"title": "Paper B", "year": 2024, "significance": "Sig B"}],
            "trends": [{"topic": "Trend C", "description": "Desc C"}],
        }
        result = _build_discovery_summary(discovery)
        assert "经典文献:" in result
        assert "近期文献:" in result
        assert "研究趋势:" in result

    def test_truncation(self):
        """Ensure max_items limits how many items are included."""
        discovery = {
            "seminal_works": [
                {"title": f"Paper {i}", "year": 2020, "significance": f"Sig {i}"}
                for i in range(20)
            ],
            "recent_works": [],
            "trends": [],
        }
        result = _build_discovery_summary(discovery, max_items=3)
        # Only 3 papers should appear (plus the header line)
        seminal_lines = [line for line in result.split("\n") if line.startswith("  - ")]
        assert len(seminal_lines) == 3

    def test_missing_fields_use_defaults(self):
        discovery = {
            "seminal_works": [{"title": "X"}],
            "recent_works": [],
            "trends": [],
        }
        result = _build_discovery_summary(discovery)
        assert "X" in result
        # Missing year and significance should not cause errors
        assert "经典文献:" in result


# ---------------------------------------------------------------------------
# _determine_generation_mode
# ---------------------------------------------------------------------------
class TestDetermineGenerationMode:
    def test_all_true(self):
        steps = {
            "discovery": True,
            "gap_mining": True,
            "synthesis": True,
            "cross_validation": True,
        }
        assert _determine_generation_mode(steps) == "llm"

    def test_some_true(self):
        steps = {
            "discovery": True,
            "gap_mining": False,
            "synthesis": True,
            "cross_validation": False,
        }
        assert _determine_generation_mode(steps) == "partial_llm"

    def test_one_true(self):
        steps = {
            "discovery": True,
            "gap_mining": False,
            "synthesis": False,
            "cross_validation": False,
        }
        assert _determine_generation_mode(steps) == "partial_llm"

    def test_none_true(self):
        steps = {
            "discovery": False,
            "gap_mining": False,
            "synthesis": False,
            "cross_validation": False,
        }
        assert _determine_generation_mode(steps) == "template_fallback"

    def test_empty_steps(self):
        """Empty dict means 0 succeeded == 0 total => llm (0==0)."""
        assert _determine_generation_mode({}) == "llm"


# ---------------------------------------------------------------------------
# Phase 1: Discovery merge logic (handling exceptions from asyncio.gather)
# ---------------------------------------------------------------------------
class TestPhase1Discovery:
    @pytest.mark.asyncio
    async def test_all_tasks_succeed(self):
        """When all 3 parallel tasks succeed, results are merged."""
        with patch(
            "src.agents.graphs.thesis.deep_research._scout_seminal_works",
            new_callable=AsyncMock,
            return_value=[{"title": "Seminal A"}],
        ), patch(
            "src.agents.graphs.thesis.deep_research._scout_recent_works",
            new_callable=AsyncMock,
            return_value=[{"title": "Recent B"}],
        ), patch(
            "src.agents.graphs.thesis.deep_research._analyze_trends",
            new_callable=AsyncMock,
            return_value=[{"topic": "Trend C"}],
        ):
            result = await _phase1_discovery("NLP", "计算机科学", [], None)

        assert result["seminal_works"] == [{"title": "Seminal A"}]
        assert result["recent_works"] == [{"title": "Recent B"}]
        assert result["trends"] == [{"topic": "Trend C"}]

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        """When some tasks fail, successful results are still returned."""
        with patch(
            "src.agents.graphs.thesis.deep_research._scout_seminal_works",
            new_callable=AsyncMock,
            return_value=[{"title": "Seminal A"}],
        ), patch(
            "src.agents.graphs.thesis.deep_research._scout_recent_works",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM timeout"),
        ), patch(
            "src.agents.graphs.thesis.deep_research._analyze_trends",
            new_callable=AsyncMock,
            return_value=[{"topic": "Trend C"}],
        ):
            result = await _phase1_discovery("NLP", "计算机科学", [], None)

        assert result["seminal_works"] == [{"title": "Seminal A"}]
        assert result["recent_works"] == []  # Failed task returns empty
        assert result["trends"] == [{"topic": "Trend C"}]

    @pytest.mark.asyncio
    async def test_all_tasks_fail(self):
        """When all tasks fail, empty lists are returned."""
        with patch(
            "src.agents.graphs.thesis.deep_research._scout_seminal_works",
            new_callable=AsyncMock,
            side_effect=RuntimeError("fail"),
        ), patch(
            "src.agents.graphs.thesis.deep_research._scout_recent_works",
            new_callable=AsyncMock,
            side_effect=RuntimeError("fail"),
        ), patch(
            "src.agents.graphs.thesis.deep_research._analyze_trends",
            new_callable=AsyncMock,
            side_effect=RuntimeError("fail"),
        ):
            result = await _phase1_discovery("NLP", "计算机科学", [], None)

        assert result["seminal_works"] == []
        assert result["recent_works"] == []
        assert result["trends"] == []

    @pytest.mark.asyncio
    async def test_non_list_results_become_empty(self):
        """If a task returns a non-list value, it becomes an empty list."""
        with patch(
            "src.agents.graphs.thesis.deep_research._scout_seminal_works",
            new_callable=AsyncMock,
            return_value="not a list",
        ), patch(
            "src.agents.graphs.thesis.deep_research._scout_recent_works",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "src.agents.graphs.thesis.deep_research._analyze_trends",
            new_callable=AsyncMock,
            return_value=[{"topic": "Valid"}],
        ):
            result = await _phase1_discovery("NLP", "计算机科学", [], None)

        assert result["seminal_works"] == []
        assert result["recent_works"] == []
        assert result["trends"] == [{"topic": "Valid"}]
