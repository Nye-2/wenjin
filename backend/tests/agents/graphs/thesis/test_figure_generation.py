"""Tests for figure generation sub-graph."""

from src.agents.graphs.thesis.figure_generation import (
    _build_fallback_source,
    _parse_json_response,
    _resolve_strategy,
)


# ---------------------------------------------------------------------------
# _resolve_strategy
# ---------------------------------------------------------------------------
class TestResolveStrategy:
    def test_mermaid_types(self):
        assert _resolve_strategy("flowchart") == "mermaid"
        assert _resolve_strategy("architecture") == "mermaid"
        assert _resolve_strategy("diagram") == "mermaid"

    def test_python_types(self):
        assert _resolve_strategy("data_visualization") == "python"
        assert _resolve_strategy("data_chart") == "python"
        assert _resolve_strategy("chart") == "python"
        assert _resolve_strategy("graph") == "python"

    def test_kling_types(self):
        assert _resolve_strategy("concept_map") == "kling"
        assert _resolve_strategy("concept") == "kling"

    def test_unknown_defaults_to_mermaid(self):
        assert _resolve_strategy("unknown_type") == "mermaid"
        assert _resolve_strategy("") == "mermaid"
        assert _resolve_strategy("random") == "mermaid"

    def test_case_insensitive(self):
        assert _resolve_strategy("Flowchart") == "mermaid"
        assert _resolve_strategy("CHART") == "python"
        assert _resolve_strategy(" Concept_Map ") == "kling"


# ---------------------------------------------------------------------------
# _build_fallback_source
# ---------------------------------------------------------------------------
class TestBuildFallbackSource:
    def test_mermaid_source_has_flowchart(self):
        source = _build_fallback_source("mermaid", "测试流程")
        assert "flowchart" in source
        assert "测试流程" in source

    def test_python_source_has_matplotlib(self):
        source = _build_fallback_source("python", "实验对比")
        assert "matplotlib" in source
        assert "plt.savefig" in source
        assert "/workspace/output/chart.png" in source

    def test_kling_source_has_prompt_text(self):
        source = _build_fallback_source("kling", "概念架构")
        assert "概念架构" in source
        assert "学术" in source

    def test_empty_description_uses_default(self):
        source_mermaid = _build_fallback_source("mermaid", "")
        assert "flowchart" in source_mermaid

        source_python = _build_fallback_source("python", "")
        assert "matplotlib" in source_python

        source_kling = _build_fallback_source("kling", "")
        assert "学术" in source_kling

    def test_unknown_strategy_defaults_to_mermaid(self):
        source = _build_fallback_source("unknown", "测试")
        assert "flowchart" in source

    def test_python_source_has_title(self):
        source = _build_fallback_source("python", "性能对比图")
        assert "性能对比图" in source

    def test_kling_source_truncates_long_description(self):
        long_desc = "这是一段很长的描述" * 50
        source = _build_fallback_source("kling", long_desc)
        # Should not contain the full description (truncated to 120)
        assert len(source) < len(long_desc) + 200


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


# ---------------------------------------------------------------------------
# Fallback source content verification
# ---------------------------------------------------------------------------
class TestFallbackSourceContent:
    def test_mermaid_has_research_flow_nodes(self):
        source = _build_fallback_source("mermaid", "研究方法")
        assert "方法设计" in source
        assert "实验验证" in source
        assert "结果分析" in source

    def test_python_has_bar_chart_structure(self):
        source = _build_fallback_source("python", "数据对比")
        assert "ax.bar" in source
        assert "ax.set_ylim" in source
        assert "plt.tight_layout()" in source

    def test_kling_mentions_entities_and_relations(self):
        source = _build_fallback_source("kling", "知识图谱")
        assert "核心实体" in source
        assert "关键关系" in source
