# tests/thesis/workflow/nodes/test_section_writer.py
"""Tests for section writer node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState, SectionPlan, SectionContent
from src.thesis.workflow.nodes.section_writer import (
    section_writer_node,
    get_next_section_index,
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
        "section_plans": [
            SectionPlan(index=1, title="绪论", target_words=2000),
            SectionPlan(index=2, title="相关工作", target_words=3000),
        ],
        "writing_order": [1, 2],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "writing",
        "progress": 0.2,
        "errors": [],
    }


def test_get_next_section_index(sample_state):
    """Test getting next section to write."""
    # No sections written yet
    idx = get_next_section_index(sample_state)
    assert idx == 1  # First in writing_order

    # After first section completed
    sample_state["sections"].append(
        SectionContent(index=1, title="绪论", content="...", status="completed")
    )
    idx = get_next_section_index(sample_state)
    assert idx == 2  # Second in writing_order


def test_get_next_section_index_all_completed(sample_state):
    """Test returns None when all sections completed."""
    sample_state["sections"] = [
        SectionContent(index=1, title="绪论", content="...", status="completed"),
        SectionContent(index=2, title="相关工作", content="...", status="completed"),
    ]
    idx = get_next_section_index(sample_state)
    assert idx is None


def test_section_writer_marks_section_completed_with_content(sample_state):
    """section_writer_node should produce completed sections with real content."""
    result = section_writer_node(sample_state)
    sections = result.get("sections", [])
    assert len(sections) == 1
    section = sections[0]
    assert section.status == "completed"
    assert section.content  # Must have non-empty content
    assert section.word_count > 0


def test_section_writer_completed_section_preserves_title(sample_state):
    """Completed section should preserve the title from the plan."""
    result = section_writer_node(sample_state)
    section = result["sections"][0]
    assert section.title == "绪论"
