"""Tests for OutputMappingResolver — template expression resolution."""

from src.agents.lead_agent.v2.output_mapping import _dot_get, _resolve_value


class TestDotGet:
    def test_simple_key(self):
        assert _dot_get({"a": 1}, "a") == 1

    def test_nested_path(self):
        assert _dot_get({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_missing_key_returns_none(self):
        assert _dot_get({"a": 1}, "b") is None

    def test_missing_nested_returns_none(self):
        assert _dot_get({"a": {"b": 1}}, "a.c") is None

    def test_none_input_returns_none(self):
        assert _dot_get(None, "a") is None

    def test_list_value_returned_as_is(self):
        data = {"authors": ["Smith", "Lee"]}
        assert _dot_get(data, "authors") == ["Smith", "Lee"]


class TestResolveValue:
    def test_literal_string(self):
        assert _resolve_value("hello", {}, None) == "hello"

    def test_literal_number_stays_string(self):
        assert _resolve_value("42", {}, None) == "42"

    def test_output_template(self):
        output = {"title": "Deep Learning"}
        assert _resolve_value("{{output.title}}", output, None) == "Deep Learning"

    def test_output_nested_template(self):
        output = {"meta": {"keywords": ["ML"]}}
        assert _resolve_value("{{output.meta.keywords}}", output, None) == ["ML"]

    def test_item_template(self):
        item = {"name": "Paper A"}
        assert _resolve_value("{{item.name}}", {}, item) == "Paper A"

    def test_missing_output_path_returns_none(self):
        assert _resolve_value("{{output.missing}}", {}, None) is None

    def test_list_value_returned_directly(self):
        output = {"authors": ["Smith", "Lee"]}
        result = _resolve_value("{{output.authors}}", output, None)
        assert result == ["Smith", "Lee"]

    def test_interpolated_string(self):
        output = {"name": "Methodology", "summary": "Core DL methods"}
        result = _resolve_value("{{output.name}}：{{output.summary}}", output, None)
        assert result == "Methodology：Core DL methods"

    def test_interpolated_with_item(self):
        item = {"name": "Methods", "summary": "DL approaches"}
        result = _resolve_value("{{item.name}} — {{item.summary}}", {}, item)
        assert result == "Methods — DL approaches"

    def test_unrecognized_prefix_returns_none(self):
        result = _resolve_value("{{config.base_url}}", {}, None)
        assert result is None

    def test_interpolated_missing_field_becomes_empty(self):
        output = {"name": "Test"}
        result = _resolve_value("{{output.name}}：{{output.missing}}", output, None)
        assert result == "Test："


from src.agents.lead_agent.v2.output_mapping import OutputMappingResolver  # noqa: E402


def _make_graph(phases: list[dict]) -> dict:
    return {"phases": phases}


class TestOutputMappingResolverLibraryItem:
    def test_iterate_library_items(self):
        graph = _make_graph([
            {"name": "search", "tasks": [
                {
                    "name": "lit_search",
                    "subagent_type": "searcher",
                    "outputs": [{
                        "kind": "library_item",
                        "iterate_on": "output.papers",
                        "default_checked": True,
                        "mapping": {
                            "title": "{{item.title}}",
                            "authors": "{{item.authors}}",
                            "year": "{{item.year}}",
                            "doi": "{{item.doi}}",
                            "abstract": "{{item.abstract}}",
                        },
                    }],
                },
            ]},
        ])
        node_results = {
            "lit_search": {
                "output": {
                    "papers": [
                        {"title": "Paper A", "authors": ["Smith"], "year": 2024, "doi": "10.1/a"},
                        {"title": "Paper B", "authors": ["Lee", "Wang"], "year": 2023, "doi": None},
                    ],
                },
            },
        }
        result = OutputMappingResolver().resolve(graph, node_results)

        assert len(result) == 2
        assert result[0].kind == "library_item"
        assert result[0].data.title == "Paper A"
        assert result[0].data.authors == ["Smith"]
        assert result[0].data.year == 2024
        assert result[0].default_checked is True
        assert result[0].id == "lit_search-library_item-0"
        assert result[1].data.title == "Paper B"
        assert result[1].data.authors == ["Lee", "Wang"]

    def test_no_outputs_declaration_produces_empty(self):
        graph = _make_graph([
            {"name": "search", "tasks": [
                {"name": "search", "subagent_type": "searcher"},
            ]},
        ])
        node_results = {"search": {"output": {"papers": []}}}
        result = OutputMappingResolver().resolve(graph, node_results)
        assert result == []

    def test_missing_node_result_skipped(self):
        graph = _make_graph([
            {"name": "search", "tasks": [
                {
                    "name": "missing_task",
                    "subagent_type": "searcher",
                    "outputs": [{
                        "kind": "library_item",
                        "iterate_on": "output.papers",
                        "mapping": {"title": "{{item.title}}", "authors": "{{item.authors}}"},
                    }],
                },
            ]},
        ])
        result = OutputMappingResolver().resolve(graph, {})
        assert result == []

    def test_iterate_on_empty_array_produces_nothing(self):
        graph = _make_graph([
            {"name": "search", "tasks": [
                {
                    "name": "lit_search",
                    "subagent_type": "searcher",
                    "outputs": [{
                        "kind": "library_item",
                        "iterate_on": "output.papers",
                        "mapping": {"title": "{{item.title}}", "authors": "{{item.authors}}"},
                    }],
                },
            ]},
        ])
        node_results = {"lit_search": {"output": {"papers": []}}}
        result = OutputMappingResolver().resolve(graph, node_results)
        assert result == []


class TestOutputMappingResolverDocument:
    def test_single_document(self):
        graph = _make_graph([
            {"name": "write", "tasks": [
                {
                    "name": "draft",
                    "subagent_type": "react",
                    "outputs": [{
                        "kind": "document",
                        "default_checked": False,
                        "mapping": {
                            "name": "{{output.title}}",
                            "mime_type": "text/markdown",
                            "storage_path": "{{output.file_path}}",
                            "size_bytes": "{{output.size_bytes}}",
                            "doc_kind": "draft",
                        },
                    }],
                },
            ]},
        ])
        node_results = {
            "draft": {
                "output": {
                    "title": "综述初稿",
                    "file_path": "/tmp/draft.md",
                    "size_bytes": 2048,
                },
            },
        }
        result = OutputMappingResolver().resolve(graph, node_results)

        assert len(result) == 1
        assert result[0].kind == "document"
        assert result[0].data.name == "综述初稿"
        assert result[0].data.mime_type == "text/markdown"
        assert result[0].data.storage_path == "/tmp/draft.md"
        assert result[0].data.size_bytes == 2048
        assert result[0].data.doc_kind == "draft"
        assert result[0].default_checked is False


class TestOutputMappingResolverMemoryFact:
    def test_memory_facts(self):
        graph = _make_graph([
            {"name": "analyze", "tasks": [
                {
                    "name": "extract",
                    "subagent_type": "react",
                    "outputs": [{
                        "kind": "memory_fact",
                        "iterate_on": "output.facts",
                        "default_checked": False,
                        "mapping": {
                            "content": "{{item.text}}",
                            "category": "{{item.category}}",
                            "confidence": "{{item.confidence}}",
                        },
                    }],
                },
            ]},
        ])
        node_results = {
            "extract": {
                "output": {
                    "facts": [
                        {"text": "User prefers APA", "category": "preference", "confidence": 0.9},
                    ],
                },
            },
        }
        result = OutputMappingResolver().resolve(graph, node_results)

        assert len(result) == 1
        assert result[0].kind == "memory_fact"
        assert result[0].data.content == "User prefers APA"
        assert result[0].data.category == "preference"
        assert result[0].data.confidence == 0.9


class TestOutputMappingResolverDecision:
    def test_decision(self):
        graph = _make_graph([
            {"name": "decide", "tasks": [
                {
                    "name": "choose",
                    "subagent_type": "react",
                    "outputs": [{
                        "kind": "decision",
                        "mapping": {
                            "key": "methodology",
                            "value": "{{output.chosen_method}}",
                        },
                    }],
                },
            ]},
        ])
        node_results = {"choose": {"output": {"chosen_method": "quantitative"}}}
        result = OutputMappingResolver().resolve(graph, node_results)

        assert len(result) == 1
        assert result[0].kind == "decision"
        assert result[0].data.key == "methodology"
        assert result[0].data.value == "quantitative"


class TestOutputMappingResolverTask:
    def test_follow_up_tasks(self):
        graph = _make_graph([
            {"name": "plan", "tasks": [
                {
                    "name": "identify_tasks",
                    "subagent_type": "react",
                    "outputs": [{
                        "kind": "task",
                        "iterate_on": "output.todos",
                        "mapping": {
                            "title": "{{item.title}}",
                            "description": "{{item.detail}}",
                            "priority": "{{item.priority}}",
                        },
                    }],
                },
            ]},
        ])
        node_results = {
            "identify_tasks": {
                "output": {
                    "todos": [
                        {"title": "补充实验", "detail": "跑 ablation", "priority": 1},
                        {"title": "更新图表", "detail": "Figure 3", "priority": 0},
                    ],
                },
            },
        }
        result = OutputMappingResolver().resolve(graph, node_results)

        assert len(result) == 2
        assert result[0].kind == "task"
        assert result[0].data.title == "补充实验"
        assert result[0].data.priority == 1
        assert result[1].data.title == "更新图表"


class TestCollectOutputsIntegration:
    def test_deep_research_produces_library_items(self):
        graph = _make_graph([
            {"name": "discover", "tasks": [
                {
                    "name": "search",
                    "subagent_type": "searcher",
                    "outputs": [{
                        "kind": "library_item",
                        "iterate_on": "output.papers",
                        "mapping": {
                            "title": "{{item.title}}",
                            "authors": "{{item.authors}}",
                            "year": "{{item.year}}",
                            "doi": "{{item.doi}}",
                        },
                    }],
                },
            ]},
            {"name": "synthesize", "depends_on": ["discover"], "tasks": [
                {
                    "name": "write",
                    "subagent_type": "react",
                    "outputs": [{
                        "kind": "document",
                        "mapping": {
                            "name": "文献综述",
                            "mime_type": "text/markdown",
                            "storage_path": "{{output.file_path}}",
                            "size_bytes": "{{output.size_bytes}}",
                            "doc_kind": "literature_review",
                        },
                    }],
                },
            ]},
        ])
        node_results = {
            "search": {
                "output": {
                    "papers": [
                        {"title": "Paper 1", "authors": ["A"], "year": 2024, "doi": "10.1/a"},
                        {"title": "Paper 2", "authors": ["B"], "year": 2023, "doi": None},
                    ],
                },
            },
            "write": {
                "output": {"file_path": "/tmp/review.md", "size_bytes": 4096},
            },
        }
        result = OutputMappingResolver().resolve(graph, node_results)

        assert len(result) == 3
        assert result[0].kind == "library_item"
        assert result[0].data.title == "Paper 1"
        assert result[1].kind == "library_item"
        assert result[1].data.title == "Paper 2"
        assert result[2].kind == "document"
        assert result[2].data.name == "文献综述"
