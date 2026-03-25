"""Tests for figure generation sub-graph helpers."""

from src.agents.graphs.thesis.figure_generation import (
    _parse_json_response,
    _resolve_strategy,
    _select_execution_strategy,
)


class TestResolveStrategy:
    def test_known_mappings(self):
        assert _resolve_strategy("flowchart") == "mermaid"
        assert _resolve_strategy("chart") == "python"
        assert _resolve_strategy("concept_map") == "kling"

    def test_unknown_defaults_to_mermaid(self):
        assert _resolve_strategy("unknown") == "mermaid"

    def test_case_insensitive(self):
        assert _resolve_strategy(" Concept_Map ") == "kling"


class TestParseJsonResponse:
    def test_valid(self):
        assert _parse_json_response('{"key":"val"}') == {"key": "val"}

    def test_markdown_fenced(self):
        assert _parse_json_response("```json\n{\"k\":1}\n```") == {"k": 1}

    def test_invalid(self):
        assert _parse_json_response("not json") is None


class TestSelectExecutionStrategy:
    def test_keep_strategy_when_provider_ready(self, monkeypatch):
        from src.agents.graphs.thesis import figure_generation

        monkeypatch.setattr(figure_generation, "_provider_ready", lambda strategy: strategy == "kling")
        strategy, reason = _select_execution_strategy("kling")
        assert strategy == "kling"
        assert reason is None

    def test_return_reason_when_provider_not_ready(self, monkeypatch):
        from src.agents.graphs.thesis import figure_generation

        monkeypatch.setattr(figure_generation, "_provider_ready", lambda _strategy: False)
        strategy, reason = _select_execution_strategy("python")
        assert strategy == "python"
        assert reason == "provider for python not ready"
