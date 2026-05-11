# Capability Output Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `_collect_outputs()` so capability executions produce typed `ResultOutput` objects from subagent node results, enabling the ResultCard commit flow.

**Architecture:** New `OutputMappingResolver` class parses `outputs` declarations from capability YAML's `graph_template`, resolves `{{output.*}}` / `{{item.*}}` template expressions against actual `node_results`, and returns a flat `list[ResultOutput]`. Wired into `LeadAgentRuntime._collect_outputs()`. Supports interpolated strings (mixed `{{...}}` + literal text).

**Tech Stack:** Python 3.13, Pydantic v2, PyYAML

**Status:** COMPLETED (2026-05-11). All 6 tasks done + frontend bridge fix (useChatStream.ts).

---

### Task 1: OutputMappingResolver core — template resolution

**Files:**
- Create: `backend/src/agents/lead_agent/v2/output_mapping.py`
- Test: `backend/tests/agents/lead_agent/v2/test_output_mapping.py`

- [ ] **Step 1: Write failing tests for template resolution**

Create `backend/tests/agents/lead_agent/v2/test_output_mapping.py`:

```python
"""Tests for OutputMappingResolver — template expression resolution."""
import pytest

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_output_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.lead_agent.v2.output_mapping'`

- [ ] **Step 3: Create output_mapping.py with template resolution helpers**

Create `backend/src/agents/lead_agent/v2/output_mapping.py`:

```python
"""OutputMappingResolver — transforms subagent outputs into typed ResultOutput objects."""
from __future__ import annotations

import logging
from typing import Any

from src.agents.contracts.task_report import (
    DecisionData,
    DecisionOutput,
    DocumentData,
    DocumentOutput,
    LibraryItemData,
    LibraryItemOutput,
    MemoryFactData,
    MemoryFactOutput,
    ResultOutput,
    TaskData,
    TaskOutput,
)

logger = logging.getLogger(__name__)


def _dot_get(obj: Any, path: str) -> Any:
    """Resolve a dot-separated path against a dict. Returns None on any failure."""
    if obj is None:
        return None
    current = obj
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def _resolve_value(expr: str, output: dict, item: dict | None = None) -> Any:
    """Resolve a template expression or return a literal string."""
    if isinstance(expr, str) and expr.startswith("{{") and expr.endswith("}}"):
        path = expr[2:-2].strip()
        if path.startswith("output."):
            return _dot_get(output, path[7:])
        if path.startswith("item."):
            return _dot_get(item, path[5:])
    return expr
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_output_mapping.py::TestDotGet tests/agents/lead_agent/v2/test_output_mapping.py::TestResolveValue -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin/backend
git add src/agents/lead_agent/v2/output_mapping.py tests/agents/lead_agent/v2/test_output_mapping.py
git commit -m "feat: add output_mapping module with template resolution helpers"
```

---

### Task 2: OutputMappingResolver — resolve method

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/output_mapping.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_output_mapping.py`

- [ ] **Step 1: Write failing tests for resolve()**

Append to `backend/tests/agents/lead_agent/v2/test_output_mapping.py`:

```python
from src.agents.lead_agent.v2.output_mapping import OutputMappingResolver


def _make_graph(phases: list[dict]) -> dict:
    return {"phases": phases}


class TestOutputMappingResolverLibraryItem:
    """Test library_item output kind with iterate_on."""

    def test_iterate_library_items(self):
        graph = _make_graph([
            {"name": "search", "tasks": [
                {
                    "name": "lit_search",
                    "subagent_type": "scholar_searcher",
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
                {"name": "search", "subagent_type": "scholar_searcher"},
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
                    "subagent_type": "scholar_searcher",
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
                    "subagent_type": "scholar_searcher",
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
    """Test document output kind without iterate_on (single output)."""

    def test_single_document(self):
        graph = _make_graph([
            {"name": "write", "tasks": [
                {
                    "name": "draft",
                    "subagent_type": "critical_writer",
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
                    "subagent_type": "clusterer",
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
                    "subagent_type": "outliner",
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
                    "subagent_type": "outliner",
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
                        {"title": "补充实验", "detail": "跑 ablation", "priority": "high"},
                        {"title": "更新图表", "detail": "Figure 3", "priority": "normal"},
                    ],
                },
            },
        }
        result = OutputMappingResolver().resolve(graph, node_results)

        assert len(result) == 2
        assert result[0].kind == "task"
        assert result[0].data.title == "补充实验"
        assert result[0].data.priority == "high"
        assert result[1].data.title == "更新图表"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_output_mapping.py::TestOutputMappingResolverLibraryItem -v`
Expected: FAIL — `ImportError` or `AttributeError` since `OutputMappingResolver` doesn't exist yet

- [ ] **Step 3: Implement OutputMappingResolver.resolve()**

Add to `backend/src/agents/lead_agent/v2/output_mapping.py`:

```python
_KIND_TO_DATA_MODEL = {
    "library_item": ("library_item", LibraryItemData, LibraryItemOutput),
    "document": ("document", DocumentData, DocumentOutput),
    "memory_fact": ("memory_fact", MemoryFactData, MemoryFactOutput),
    "decision": ("decision", DecisionData, DecisionOutput),
    "task": ("task", TaskData, TaskOutput),
}

_KIND_PREVIEW_TEMPLATE = {
    "library_item": lambda d: f"{d.title} — {', '.join(d.authors[:3])}" + (f", {d.year}" if d.year else ""),
    "document": lambda d: f"{d.name} ({d.mime_type})",
    "memory_fact": lambda d: (d.content[:80] + "...") if len(d.content) > 80 else d.content,
    "decision": lambda d: f"{d.key}: {d.value}",
    "task": lambda d: d.title,
}


class OutputMappingResolver:
    """Resolves output mapping declarations from capability YAML against node_results."""

    def resolve(self, graph_template: dict, node_results: dict) -> list[ResultOutput]:
        outputs: list[ResultOutput] = []
        for phase in graph_template.get("phases", []):
            for task in phase.get("tasks", []):
                task_name = task["name"]
                for decl in task.get("outputs", []):
                    outputs.extend(self._resolve_declaration(task_name, decl, node_results))
        return outputs

    def _resolve_declaration(
        self, task_name: str, decl: dict, node_results: dict,
    ) -> list[ResultOutput]:
        kind = decl["kind"]
        if kind not in _KIND_TO_DATA_MODEL:
            logger.warning("Unknown output kind '%s' in task '%s'", kind, task_name)
            return []

        _, data_model, output_model = _KIND_TO_DATA_MODEL[kind]
        mapping = decl.get("mapping", {})
        default_checked = decl.get("default_checked", True)
        iterate_on = decl.get("iterate_on")

        nr = node_results.get(task_name)
        if not isinstance(nr, dict):
            return []
        output = nr.get("output")
        if not isinstance(output, dict):
            return []

        if iterate_on:
            return self._resolve_iterated(
                task_name, kind, iterate_on, mapping, output, data_model, output_model, default_checked,
            )
        return self._resolve_single(
            task_name, kind, mapping, output, None, data_model, output_model, default_checked, 0,
        )

    def _resolve_iterated(
        self, task_name: str, kind: str, iterate_on: str, mapping: dict,
        output: dict, data_model: type, output_model: type, default_checked: bool,
    ) -> list[ResultOutput]:
        path = iterate_on
        if path.startswith("output."):
            path = path[7:]
        array = _dot_get(output, path)
        if not isinstance(array, list):
            return []

        results: list[ResultOutput] = []
        for i, item in enumerate(array):
            if not isinstance(item, dict):
                continue
            resolved = self._resolve_single(
                task_name, kind, mapping, output, item, data_model, output_model, default_checked, i,
            )
            results.extend(resolved)
        return results

    def _resolve_single(
        self, task_name: str, kind: str, mapping: dict,
        output: dict, item: dict | None, data_model: type, output_model: type,
        default_checked: bool, index: int,
    ) -> list[ResultOutput]:
        resolved_fields: dict[str, Any] = {}
        for field_name, expr in mapping.items():
            value = _resolve_value(expr, output, item)
            if value is not None:
                resolved_fields[field_name] = value

        try:
            data = data_model(**resolved_fields)
        except Exception:
            logger.warning(
                "Failed to construct %s data for task '%s' with fields %s",
                kind, task_name, list(resolved_fields.keys()),
                exc_info=True,
            )
            return []

        preview_fn = _KIND_PREVIEW_TEMPLATE.get(kind)
        preview = preview_fn(data) if preview_fn else str(data)

        output_id = f"{task_name}-{kind}-{index}"
        return [output_model(
            id=output_id,
            preview=preview,
            default_checked=default_checked,
            data=data,
        )]
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_output_mapping.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin/backend
git add src/agents/lead_agent/v2/output_mapping.py tests/agents/lead_agent/v2/test_output_mapping.py
git commit -m "feat: implement OutputMappingResolver with 5 output kinds"
```

---

### Task 3: Wire into LeadAgentRuntime._collect_outputs

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/runtime.py:234-241`
- Test: `backend/tests/agents/lead_agent/v2/test_output_mapping.py`

- [ ] **Step 1: Write integration test for _collect_outputs wiring**

Append to test file:

```python
class TestCollectOutputsIntegration:
    """Test that _collect_outputs produces outputs from a realistic graph + node_results."""

    def test_deep_research_produces_library_items(self):
        graph = _make_graph([
            {"name": "discover", "tasks": [
                {
                    "name": "search",
                    "subagent_type": "scholar_searcher",
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
                    "subagent_type": "critical_writer",
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
```

- [ ] **Step 2: Run test to verify it passes (no new failure — resolver already works)**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_output_mapping.py::TestCollectOutputsIntegration -v`
Expected: PASS

- [ ] **Step 3: Modify runtime.py to wire _collect_outputs**

In `backend/src/agents/lead_agent/v2/runtime.py`, replace the `_collect_outputs` method (lines 234-241):

```python
    def _collect_outputs(self, state: dict, cap: Any) -> list[ResultOutput]:
        from src.agents.lead_agent.v2.output_mapping import OutputMappingResolver

        graph_template = cap.graph_template if hasattr(cap, "graph_template") else {}
        node_results = state.get("node_results", {})
        if not graph_template or not node_results:
            return []
        return OutputMappingResolver().resolve(graph_template, node_results)
```

- [ ] **Step 4: Run existing runtime tests to verify no regressions**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin/backend
git add src/agents/lead_agent/v2/runtime.py
git commit -m "feat: wire OutputMappingResolver into LeadAgentRuntime._collect_outputs"
```

---

### Task 4: Add outputs validation to CapabilityResolver

**Files:**
- Modify: `backend/src/services/capability_resolver.py:99-165`
- Test: Create `backend/tests/services/test_capability_resolver_outputs_validation.py`

- [ ] **Step 1: Write failing validation tests**

Create `backend/tests/services/test_capability_resolver_outputs_validation.py`:

```python
"""Tests for output mapping validation in validate_capability."""
from src.services.capability_resolver import validate_capability

_VALID_KINDS = {"library_item", "document", "memory_fact", "decision", "task"}

_REQUIRED_FIELDS = {
    "library_item": {"title", "authors"},
    "document": {"name", "mime_type", "storage_path", "size_bytes"},
    "memory_fact": {"content"},
    "decision": {"key", "value"},
    "task": {"title"},
}


def _base_capability() -> dict:
    return {
        "id": "test",
        "workspace_type": "thesis",
        "graph_template": {
            "phases": [
                {
                    "name": "search",
                    "tasks": [
                        {"name": "search", "subagent_type": "scholar_searcher"},
                    ],
                },
            ],
        },
    }


class TestOutputValidation:
    def test_valid_outputs_pass(self):
        cap = _base_capability()
        cap["graph_template"]["phases"][0]["tasks"][0]["outputs"] = [
            {
                "kind": "library_item",
                "iterate_on": "output.papers",
                "mapping": {"title": "{{item.title}}", "authors": "{{item.authors}}"},
            },
        ]
        errors = validate_capability(cap)
        assert errors == []

    def test_unknown_kind_fails(self):
        cap = _base_capability()
        cap["graph_template"]["phases"][0]["tasks"][0]["outputs"] = [
            {"kind": "unknown_thing", "mapping": {"x": "y"}},
        ]
        errors = validate_capability(cap)
        assert any("unknown output kind" in e.lower() for e in errors)

    def test_missing_required_field_fails(self):
        cap = _base_capability()
        cap["graph_template"]["phases"][0]["tasks"][0]["outputs"] = [
            {"kind": "library_item", "mapping": {"title": "{{item.title}}"}},
        ]
        errors = validate_capability(cap)
        assert any("required" in e.lower() and "authors" in e for e in errors)

    def test_no_outputs_declaration_is_valid(self):
        cap = _base_capability()
        errors = validate_capability(cap)
        assert errors == []

    def test_iterate_on_without_output_prefix_warns(self):
        cap = _base_capability()
        cap["graph_template"]["phases"][0]["tasks"][0]["outputs"] = [
            {
                "kind": "library_item",
                "iterate_on": "papers",
                "mapping": {"title": "{{item.title}}", "authors": "{{item.authors}}"},
            },
        ]
        errors = validate_capability(cap)
        assert any("iterate_on" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/services/test_capability_resolver_outputs_validation.py -v`
Expected: FAIL — validation doesn't check outputs yet

- [ ] **Step 3: Add outputs validation to validate_capability()**

In `backend/src/services/capability_resolver.py`, add after the `subagent_type` check block (after line 135), inside the `for j, task in enumerate(...)` loop:

```python
                # Validate outputs declarations
                for k, out_decl in enumerate(task.get("outputs", [])):
                    out_kind = out_decl.get("kind", "")
                    if out_kind not in _VALID_OUTPUT_KINDS:
                        errors.append(
                            f"Phase '{phase_name}' task[{j}] outputs[{k}] "
                            f"has unknown output kind '{out_kind}'"
                        )
                        continue
                    required = _REQUIRED_OUTPUT_FIELDS.get(out_kind, set())
                    mapping_keys = set(out_decl.get("mapping", {}).keys())
                    missing = required - mapping_keys
                    if missing:
                        errors.append(
                            f"Phase '{phase_name}' task[{j}] outputs[{k}] "
                            f"kind '{out_kind}' missing required mapping fields: {sorted(missing)}"
                        )
                    iterate_on = out_decl.get("iterate_on", "")
                    if iterate_on and not iterate_on.startswith("output."):
                        errors.append(
                            f"Phase '{phase_name}' task[{j}] outputs[{k}] "
                            f"iterate_on must start with 'output.'"
                        )
```

Add the constants at module level (after `ALLOWED_VARS` on line 20):

```python
_VALID_OUTPUT_KINDS = {"library_item", "document", "memory_fact", "decision", "task"}

_REQUIRED_OUTPUT_FIELDS = {
    "library_item": {"title", "authors"},
    "document": {"name", "mime_type", "storage_path", "size_bytes"},
    "memory_fact": {"content"},
    "decision": {"key", "value"},
    "task": {"title"},
}
```

- [ ] **Step 4: Run validation tests**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/services/test_capability_resolver_outputs_validation.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin/backend
git add src/services/capability_resolver.py tests/services/test_capability_resolver_outputs_validation.py
git commit -m "feat: validate output mapping declarations in capability YAML"
```

---

### Task 5: Add outputs to thesis capability YAML seed files

**Files:**
- Modify: `backend/seed/capabilities/thesis/deep_research.yaml`
- Modify: `backend/seed/capabilities/thesis/outline_generate.yaml`
- Modify: `backend/seed/capabilities/thesis/section_write.yaml`
- Modify: `backend/seed/capabilities/thesis/section_revise.yaml`
- Modify: `backend/seed/capabilities/thesis/citation_manage.yaml`

- [ ] **Step 1: Read all 5 thesis YAML files to understand current structure**

Run: `cat /Users/ze/wenjin/backend/seed/capabilities/thesis/*.yaml`

- [ ] **Step 2: Add outputs to deep_research.yaml**

The `scholar_searcher` returns `{"papers": [...]}` with `{title, authors, year, doi}`.
The `critical_writer` returns `{"markdown": str}`.

In `backend/seed/capabilities/thesis/deep_research.yaml`, add `outputs` to both tasks:

```yaml
graph_template:
  phases:
    - name: discover
      tasks:
        - name: search
          subagent_type: scholar_searcher
          prompt_template: "搜索关于 {{topic}} 的文献"
          outputs:
            - kind: library_item
              iterate_on: "output.papers"
              default_checked: true
              mapping:
                title: "{{item.title}}"
                authors: "{{item.authors}}"
                year: "{{item.year}}"
                doi: "{{item.doi}}"
    - name: synthesize
      depends_on: [discover]
      tasks:
        - name: write
          subagent_type: critical_writer
          prompt_template: "写综述 {{topic}}"
          outputs:
            - kind: document
              default_checked: true
              mapping:
                name: "深度调研报告"
                mime_type: "text/markdown"
                storage_path: "deep_research.md"
                size_bytes: "0"
                doc_kind: "literature_review"
```

- [ ] **Step 3: Add outputs to outline_generate.yaml**

Read the file, find its subagent types, add appropriate outputs based on subagent output shapes.

- [ ] **Step 4: Add outputs to section_write.yaml**

Read the file, add outputs.

- [ ] **Step 5: Add outputs to section_revise.yaml**

Read the file, add outputs.

- [ ] **Step 6: Add outputs to citation_manage.yaml**

Read the file, add outputs. Note: citation_manage may produce library_item outputs.

- [ ] **Step 7: Run validation against all YAML files**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/ -q --tb=short -k "capability"`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
cd /Users/ze/wenjin/backend
git add seed/capabilities/thesis/
git commit -m "feat: add output mappings to thesis capability YAML seed files"
```

---

### Task 6: End-to-end verification

**Files:**
- No new files

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/ -q --tb=short`
Expected: Same baseline failures (9 pre-existing), no new failures

- [ ] **Step 2: Run frontend typecheck + tests**

Run: `cd /Users/ze/wenjin/frontend && npm run typecheck && npx vitest run`
Expected: 0 type errors, 155/155 tests pass

- [ ] **Step 3: Verify data flow with a manual test**

Run a quick Python script to confirm the full pipeline:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -c "
from src.agents.lead_agent.v2.output_mapping import OutputMappingResolver
import yaml, json

with open('seed/capabilities/thesis/deep_research.yaml') as f:
    cap = yaml.safe_load(f)

node_results = {
    'search': {'output': {'papers': [
        {'title': 'Federated Learning Survey', 'authors': ['Smith'], 'year': 2024, 'doi': '10.1/a'},
        {'title': 'LLM + FL Integration', 'authors': ['Lee', 'Wang'], 'year': 2023, 'doi': None},
    ]}},
    'write': {'output': {'file_path': '/tmp/draft.md', 'size_bytes': 2048}},
}

outputs = OutputMappingResolver().resolve(cap['graph_template'], node_results)
for o in outputs:
    print(f'{o.kind}: {o.preview} (checked={o.default_checked})')
print(f'Total: {len(outputs)} outputs')
"
```

Expected output:
```
library_item: Federated Learning Survey — Smith, 2024 (checked=True)
library_item: LLM + FL Integration — Lee, Wang, 2023 (checked=True)
document: 深度调研报告 (text/markdown) (checked=True)
Total: 3 outputs
```
