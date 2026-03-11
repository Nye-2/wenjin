# tests/thesis/workflow/nodes/test_literature_search.py
"""Tests for literature search node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.workflow.nodes.literature_search import (
    literature_search_node,
    check_literature_sufficiency,
)


@pytest.fixture
def sample_state() -> ThesisWorkflowState:
    """Create a sample state for testing."""
    return {
        "workspace_id": "ws-001",
        "thread_id": "thread-001",
        "paper_title": "基于深度学习的图像分类研究",
        "discipline": "计算机科学",
        "abstract_content": "摘要内容...",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "init",
        "progress": 0.0,
        "errors": [],
    }


def test_check_literature_sufficiency_empty(sample_state):
    """Test sufficiency check with no references."""
    sufficient, count = check_literature_sufficiency(sample_state)
    assert sufficient is False
    assert count == 0


def test_check_literature_sufficiency_sufficient(sample_state):
    """Test sufficiency check with enough references."""
    sample_state["references"] = [
        {"id": f"[{i}]", "title": f"Paper {i}"} for i in range(1, 16)
    ]
    sufficient, count = check_literature_sufficiency(sample_state)
    assert sufficient is True
    assert count == 15


def test_literature_search_node_sets_phase(sample_state):
    """Test that literature search sets correct phase."""
    result = literature_search_node(sample_state)
    assert result.get("current_phase") == "literature_search"
    assert result.get("progress", 0) > 0
