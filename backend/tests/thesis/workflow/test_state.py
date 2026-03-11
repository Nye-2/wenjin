"""Tests for thesis workflow state."""

import pytest
from src.thesis.workflow.state import (
    SectionPlan,
    SectionContent,
    ThesisWorkflowState,
    merge_sections,
    merge_references,
)


def test_section_plan_creation():
    """Test SectionPlan model creation."""
    plan = SectionPlan(
        index=1,
        title="绪论",
        purpose="介绍研究背景和目标",
        key_points=["背景", "问题", "目标"],
        target_words=2000,
    )
    assert plan.index == 1
    assert plan.title == "绪论"
    assert len(plan.key_points) == 3


def test_section_content_creation():
    """Test SectionContent model creation."""
    content = SectionContent(
        index=1,
        title="绪论",
        content="\\section{绪论}...",
        word_count=1500,
        references_used=["ref1", "ref2"],
        status="completed",
    )
    assert content.status == "completed"
    assert len(content.references_used) == 2


def test_merge_sections():
    """Test merge_sections reducer."""
    left = [
        SectionContent(index=1, title="绪论", content="old", status="pending"),
        SectionContent(index=2, title="相关工作", content="content2", status="completed"),
    ]
    right = [
        SectionContent(index=1, title="绪论", content="new", status="completed"),
    ]
    result = merge_sections(left, right)
    assert len(result) == 2
    # Check that index 1 was updated
    section_1 = next(s for s in result if s.index == 1)
    assert section_1.content == "new"
    assert section_1.status == "completed"


def test_merge_references():
    """Test merge_references reducer."""
    left = [{"id": "ref1", "title": "Paper 1"}]
    right = [{"id": "ref2", "title": "Paper 2"}, {"id": "ref1", "title": "Paper 1 Updated"}]
    result = merge_references(left, right)
    # Should deduplicate by id
    assert len(result) == 2
