# tests/thesis/workflow/nodes/test_assembler.py
"""Tests for LaTeX assembler node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState, SectionContent, SectionPlan
from src.thesis.workflow.nodes.assembler import (
    assemble_latex_node,
    generate_bibtex,
)


@pytest.fixture
def completed_state() -> ThesisWorkflowState:
    """Create a state with completed sections."""
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
        "references": [
            {"id": "[1]", "title": "Paper 1", "bibtex": "@article{ref1, title={Paper 1}}"},
        ],
        "citation_plan": {1: ["[1]"]},
        "sections": [
            SectionContent(index=1, title="绪论", content="\\section{绪论}...", status="completed"),
            SectionContent(index=2, title="相关工作", content="\\section{相关工作}...", status="completed"),
        ],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "writing",
        "progress": 0.80,
        "errors": [],
    }


def test_assemble_latex_node(completed_state):
    """Test assembling LaTeX from sections."""
    result = assemble_latex_node(completed_state)

    assert "final_latex" in result
    assert result["current_phase"] == "assembly"
    assert "\\documentclass" in result["final_latex"]
    assert "绪论" in result["final_latex"]


def test_generate_bibtex(completed_state):
    """Test generating BibTeX from references."""
    bib = generate_bibtex(completed_state.get("references", []))
    assert "@article{ref1" in bib
