# tests/thesis/workflow/nodes/test_figure_generator.py
"""Tests for figure generator node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState, SectionPlan
from src.thesis.workflow.nodes.figure_generator import figure_generator_node


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
        "current_phase": "figure_planning",
        "progress": 0.82,
        "errors": [],
    }


class TestFigureGeneratorNode:
    """Tests for figure_generator_node function."""

    def test_figure_generator_node_creates_stub(self, sample_state):
        """Test node creates stub figures for figure_requests."""
        sample_state["figure_requests"] = [
            {
                "id": "fig1",
                "section_index": 1,
                "figure_type": "architecture",
                "description": "系统架构图",
                "caption": "Figure 1: System Architecture",
                "strategy": "mermaid",
            },
            {
                "id": "fig2",
                "section_index": 2,
                "figure_type": "chart",
                "description": "性能对比图",
                "caption": "Figure 2: Performance Comparison",
                "strategy": "python",
            },
        ]

        result = figure_generator_node(sample_state)

        assert "generated_figures" in result
        assert len(result["generated_figures"]) == 2

        # Check first generated figure
        fig1 = result["generated_figures"][0]
        assert fig1["id"] == "fig1"
        assert fig1["request_id"] == "fig1"
        assert fig1["file_path"] == "/placeholder/fig1.pdf"
        assert "fig1.pdf" in fig1["latex_ref"]
        assert "\\includegraphics" in fig1["latex_ref"]

        # Check second generated figure
        fig2 = result["generated_figures"][1]
        assert fig2["id"] == "fig2"
        assert fig2["request_id"] == "fig2"
        assert fig2["file_path"] == "/placeholder/fig2.pdf"
        assert "fig2.pdf" in fig2["latex_ref"]

        # Check phase and progress
        assert result["current_phase"] == "figure_generation"
        assert result["progress"] == 0.85

    def test_figure_generator_empty_requests(self, sample_state):
        """Test node with no figure_requests."""
        sample_state["figure_requests"] = []

        result = figure_generator_node(sample_state)

        assert "generated_figures" in result
        assert result["generated_figures"] == []
        assert result["current_phase"] == "figure_generation"
        assert result["progress"] == 0.88

    def test_figure_generator_with_dict_requests(self, sample_state):
        """Test node with dict-style figure requests."""
        sample_state["figure_requests"] = [
            {
                "id": "arch-diagram",
                "section_index": 1,
                "figure_type": "architecture",
                "description": "系统架构",
                "caption": "Architecture Diagram",
                "strategy": "mermaid",
            },
        ]

        result = figure_generator_node(sample_state)

        assert len(result["generated_figures"]) == 1
        fig = result["generated_figures"][0]
        assert fig["id"] == "arch-diagram"
        assert fig["request_id"] == "arch-diagram"
        assert fig["file_path"] == "/placeholder/arch-diagram.pdf"

    def test_figure_generator_latex_ref_format(self, sample_state):
        """Test that latex_ref has correct format."""
        sample_state["figure_requests"] = [
            {
                "id": "test-fig",
                "section_index": 1,
                "figure_type": "flowchart",
                "description": "Test figure",
                "caption": "Test Caption",
                "strategy": "mermaid",
            },
        ]

        result = figure_generator_node(sample_state)

        fig = result["generated_figures"][0]
        # Verify latex_ref includes width parameter and figure id
        assert "width=0.8\\textwidth" in fig["latex_ref"]
        assert "test-fig.pdf" in fig["latex_ref"]
