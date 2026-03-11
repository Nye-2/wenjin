# tests/thesis/workflow/nodes/test_compiler.py
"""Tests for LaTeX compiler node (stub implementation)."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState, SectionContent, SectionPlan
from src.thesis.workflow.nodes.compiler import compile_latex_node


@pytest.fixture
def state_with_latex() -> ThesisWorkflowState:
    """Create a state with final_latex content."""
    return {
        "workspace_id": "ws-001",
        "thread_id": "thread-001",
        "paper_title": "基于深度学习的图像分类研究",
        "discipline": "计算机科学",
        "abstract_content": "摘要内容...",
        "framework_json": {},
        "section_plans": [
            SectionPlan(index=1, title="绪论", target_words=2000),
        ],
        "writing_order": [1],
        "references": [],
        "citation_plan": {},
        "sections": [
            SectionContent(index=1, title="绪论", content="\\section{绪论}...", status="completed"),
        ],
        "figure_requests": [],
        "generated_figures": [],
        "final_latex": "\\documentclass{article}\\begin{document}test\\end{document}",
        "bib_content": "@article{ref1, title={Paper 1}}",
        "current_phase": "assembly",
        "progress": 0.95,
        "errors": [],
    }


@pytest.fixture
def state_without_latex() -> ThesisWorkflowState:
    """Create a state without final_latex content."""
    return {
        "workspace_id": "ws-002",
        "thread_id": "thread-002",
        "paper_title": "测试论文",
        "discipline": "计算机科学",
        "abstract_content": "摘要",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "writing",
        "progress": 0.50,
        "errors": [],
    }


def test_compile_latex_node_creates_pdf_stub(state_with_latex):
    """Test that compiler node creates a stub PDF path when final_latex exists."""
    result = compile_latex_node(state_with_latex)

    # Should return a stub PDF path
    assert "pdf_path" in result
    assert result["pdf_path"] == "/sandbox/ws-001/thesis.pdf"

    # Should set current_phase to compile
    assert result["current_phase"] == "compile"

    # Should set progress to 1.0 (complete)
    assert result["progress"] == 1.0


def test_compile_latex_node_missing_latex(state_without_latex):
    """Test that compiler node handles missing final_latex gracefully."""
    result = compile_latex_node(state_without_latex)

    # Should not have pdf_path
    assert "pdf_path" not in result or result.get("pdf_path") is None

    # Should have an error in errors list
    assert "errors" in result
    assert len(result["errors"]) > 0
    assert any("final_latex" in err.lower() or "latex" in err.lower() for err in result["errors"])
