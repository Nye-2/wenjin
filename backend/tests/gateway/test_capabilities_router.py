"""Tests for capabilities router serialization."""
from unittest.mock import MagicMock

from src.gateway.routers.capabilities import _capability_to_dict


def test_capability_to_dict_includes_ui_meta_and_runtime():
    cap = MagicMock()
    cap.id = "deep_research"
    cap.workspace_type = "thesis"
    cap.enabled = True
    cap.display_name = "深度调研"
    cap.description = "desc"
    cap.intent_description = "intent"
    cap.trigger_phrases = []
    cap.required_decisions = []
    cap.brief_schema = None
    cap.graph_template = None
    cap.ui_meta = {"icon": "search", "order": 0}
    cap.runtime = {"mode": "compute_agentic"}
    cap.dashboard_meta = {"status_kind": "deep_research"}
    cap.notes = None

    result = _capability_to_dict(cap)

    assert result["id"] == "deep_research"
    assert result["workspace_type"] == "thesis"
    assert result["enabled"] is True
    assert result["ui_meta"] == {"icon": "search", "order": 0}
    assert result["runtime"] == {"mode": "compute_agentic"}
    assert result["dashboard_meta"] == {"status_kind": "deep_research"}
    assert result["notes"] is None
