"""Tests for output mapping validation in validate_capability."""
from src.services.capability_resolver import validate_capability

_REGISTRY = ["searcher", "react"]


def _base_capability() -> dict:
    return {
        "id": "test",
        "workspace_type": "thesis",
        "graph_template": {
            "phases": [
                {
                    "name": "search",
                    "tasks": [
                        {"name": "search", "subagent_type": "searcher"},
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
        errors = validate_capability(cap, subagent_registry=_REGISTRY)
        assert errors == []

    def test_unknown_kind_fails(self):
        cap = _base_capability()
        cap["graph_template"]["phases"][0]["tasks"][0]["outputs"] = [
            {"kind": "unknown_thing", "mapping": {"x": "y"}},
        ]
        errors = validate_capability(cap, subagent_registry=_REGISTRY)
        assert any("unknown output kind" in e.lower() for e in errors)

    def test_missing_required_field_fails(self):
        cap = _base_capability()
        cap["graph_template"]["phases"][0]["tasks"][0]["outputs"] = [
            {"kind": "library_item", "mapping": {"title": "{{item.title}}"}},
        ]
        errors = validate_capability(cap, subagent_registry=_REGISTRY)
        assert any("required" in e.lower() and "authors" in e for e in errors)

    def test_no_outputs_declaration_is_valid(self):
        cap = _base_capability()
        errors = validate_capability(cap, subagent_registry=_REGISTRY)
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
        errors = validate_capability(cap, subagent_registry=_REGISTRY)
        assert any("iterate_on" in e for e in errors)

    def test_unknown_field_fails(self):
        cap = _base_capability()
        cap["graph_template"]["phases"][0]["tasks"][0]["outputs"] = [
            {
                "kind": "library_item",
                "iterate_on": "output.papers",
                "mapping": {
                    "title": "{{item.title}}",
                    "authors": "{{item.authors}}",
                    "bogus_field": "{{item.bogus}}",
                },
            },
        ]
        errors = validate_capability(cap, subagent_registry=_REGISTRY)
        assert any("Unknown field" in e and "bogus_field" in e for e in errors)
