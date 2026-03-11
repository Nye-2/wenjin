# tests/thesis/workflow/nodes/test_figure_planner.py
"""Tests for figure planner node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState, SectionPlan, SectionContent
from src.thesis.workflow.nodes.figure_planner import (
    PLACEHOLDER_PATTERN,
    extract_figure_placeholders,
    determine_strategy,
    figure_planner_node,
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
            SectionPlan(index=3, title="系统设计", target_words=4000),
        ],
        "writing_order": [1, 2, 3],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "figures",
        "progress": 0.80,
        "errors": [],
    }


class TestPlaceholderPattern:
    """Tests for PLACEHOLDER_PATTERN regex."""

    def test_matches_standard_placeholder(self):
        """Test matching a standard placeholder."""
        content = "% [FIGURE:fig1|architecture|系统架构图|Figure 1: System Architecture]"
        match = PLACEHOLDER_PATTERN.search(content)
        assert match is not None
        assert match.group(1) == "fig1"
        assert match.group(2) == "architecture"
        assert match.group(3) == "系统架构图"
        assert match.group(4) == "Figure 1: System Architecture"

    def test_matches_with_spaces(self):
        """Test matching placeholder with spaces after percent."""
        content = "%  [FIGURE:fig2|flowchart|流程图|Figure 2: Flow]"
        match = PLACEHOLDER_PATTERN.search(content)
        assert match is not None
        assert match.group(1) == "fig2"

    def test_matches_chinese_caption(self):
        """Test matching placeholder with Chinese caption."""
        content = "% [FIGURE:fig3|diagram|数据流图|图3：数据流程]"
        match = PLACEHOLDER_PATTERN.search(content)
        assert match is not None
        assert match.group(4) == "图3：数据流程"

    def test_no_match_without_percent(self):
        """Test that placeholder without percent is not matched."""
        content = "[FIGURE:fig1|architecture|desc|caption]"
        match = PLACEHOLDER_PATTERN.search(content)
        assert match is None

    def test_multiple_matches(self):
        """Test finding multiple placeholders in content."""
        content = """
        Some text here.
        % [FIGURE:fig1|architecture|系统架构|Figure 1]
        More content.
        % [FIGURE:fig2|flowchart|处理流程|Figure 2]
        End.
        """
        matches = PLACEHOLDER_PATTERN.findall(content)
        assert len(matches) == 2
        assert matches[0][0] == "fig1"
        assert matches[1][0] == "fig2"


class TestExtractFigurePlaceholders:
    """Tests for extract_figure_placeholders function."""

    def test_extract_single_placeholder(self):
        """Test extracting a single placeholder."""
        content = "Some text\n% [FIGURE:fig1|architecture|系统架构图|Figure 1]\nMore text"
        result = extract_figure_placeholders(content)
        assert len(result) == 1
        assert result[0] == {
            "id": "fig1",
            "figure_type": "architecture",
            "description": "系统架构图",
            "caption": "Figure 1",
        }

    def test_extract_multiple_placeholders(self):
        """Test extracting multiple placeholders."""
        content = """
        % [FIGURE:fig1|architecture|架构|Caption 1]
        % [FIGURE:fig2|flowchart|流程|Caption 2]
        % [FIGURE:fig3|chart|图表|Caption 3]
        """
        result = extract_figure_placeholders(content)
        assert len(result) == 3
        assert result[0]["id"] == "fig1"
        assert result[1]["id"] == "fig2"
        assert result[2]["id"] == "fig3"

    def test_extract_empty_content(self):
        """Test extracting from empty content."""
        result = extract_figure_placeholders("")
        assert result == []

    def test_extract_no_placeholders(self):
        """Test extracting from content with no placeholders."""
        content = "Just regular text\nNo placeholders here\n"
        result = extract_figure_placeholders(content)
        assert result == []

    def test_extract_with_special_chars(self):
        """Test extracting placeholder with special characters in description."""
        content = "% [FIGURE:fig-01|diagram|Model (v2.0) - Flow|Fig. 1: Model Flow]"
        result = extract_figure_placeholders(content)
        assert len(result) == 1
        assert result[0]["id"] == "fig-01"
        assert result[0]["description"] == "Model (v2.0) - Flow"


class TestDetermineStrategy:
    """Tests for determine_strategy function."""

    def test_architecture_maps_to_mermaid(self):
        """Test architecture type maps to mermaid strategy."""
        assert determine_strategy("architecture") == "mermaid"

    def test_flowchart_maps_to_mermaid(self):
        """Test flowchart type maps to mermaid strategy."""
        assert determine_strategy("flowchart") == "mermaid"

    def test_diagram_maps_to_mermaid(self):
        """Test diagram type maps to mermaid strategy."""
        assert determine_strategy("diagram") == "mermaid"

    def test_chart_maps_to_python(self):
        """Test chart type maps to python strategy."""
        assert determine_strategy("chart") == "python"

    def test_graph_maps_to_python(self):
        """Test graph type maps to python strategy."""
        assert determine_strategy("graph") == "python"

    def test_concept_maps_to_kling(self):
        """Test concept type maps to kling strategy."""
        assert determine_strategy("concept") == "kling"

    def test_unknown_type_defaults_to_mermaid(self):
        """Test unknown type defaults to mermaid strategy."""
        assert determine_strategy("unknown") == "mermaid"
        assert determine_strategy("random") == "mermaid"
        assert determine_strategy("") == "mermaid"

    def test_case_insensitive(self):
        """Test strategy mapping is case insensitive."""
        assert determine_strategy("ARCHITECTURE") == "mermaid"
        assert determine_strategy("Flowchart") == "mermaid"
        assert determine_strategy("CHART") == "python"
        assert determine_strategy("Concept") == "kling"


class TestFigurePlannerNode:
    """Tests for figure_planner_node function."""

    def test_node_with_pydantic_sections(self, sample_state):
        """Test node with Pydantic model sections."""
        sample_state["sections"] = [
            SectionContent(
                index=1,
                title="绪论",
                content="Introduction content\n% [FIGURE:fig1|architecture|系统架构|Figure 1]",
                status="completed",
            ),
            SectionContent(
                index=2,
                title="系统设计",
                content="Design section\n% [FIGURE:fig2|flowchart|处理流程|Figure 2]",
                status="completed",
            ),
        ]
        result = figure_planner_node(sample_state)

        assert "figure_requests" in result
        assert len(result["figure_requests"]) == 2

        # Check first figure request
        fig1 = result["figure_requests"][0]
        assert fig1["id"] == "fig1"
        assert fig1["section_index"] == 1
        assert fig1["figure_type"] == "architecture"
        assert fig1["description"] == "系统架构"
        assert fig1["caption"] == "Figure 1"
        assert fig1["strategy"] == "mermaid"

        # Check second figure request
        fig2 = result["figure_requests"][1]
        assert fig2["id"] == "fig2"
        assert fig2["section_index"] == 2
        assert fig2["strategy"] == "mermaid"

        assert result["current_phase"] == "figure_planning"
        assert result["progress"] == 0.82

    def test_node_with_dict_sections(self, sample_state):
        """Test node with dict sections."""
        sample_state["sections"] = [
            {
                "index": 1,
                "title": "绪论",
                "content": "% [FIGURE:fig-dict|chart|数据图表|图1]",
                "status": "completed",
            }
        ]
        result = figure_planner_node(sample_state)

        assert len(result["figure_requests"]) == 1
        fig = result["figure_requests"][0]
        assert fig["id"] == "fig-dict"
        assert fig["section_index"] == 1
        assert fig["strategy"] == "python"  # chart -> python

    def test_node_no_completed_sections(self, sample_state):
        """Test node with no completed sections."""
        sample_state["sections"] = []
        result = figure_planner_node(sample_state)

        assert result["figure_requests"] == []
        assert result["current_phase"] == "figure_planning"
        assert result["progress"] == 0.82

    def test_node_sections_with_no_placeholders(self, sample_state):
        """Test node with sections containing no placeholders."""
        sample_state["sections"] = [
            SectionContent(
                index=1,
                title="绪论",
                content="Just regular content without figures",
                status="completed",
            ),
        ]
        result = figure_planner_node(sample_state)

        assert result["figure_requests"] == []

    def test_node_multiple_figures_per_section(self, sample_state):
        """Test node with multiple figures in one section."""
        sample_state["sections"] = [
            SectionContent(
                index=1,
                title="系统设计",
                content="""
                System design section.
                % [FIGURE:arch|architecture|系统架构|Figure 1]
                Some description.
                % [FIGURE:flow|flowchart|数据流程|Figure 2]
                % [FIGURE:concept|concept|概念图|Figure 3]
                """,
                status="completed",
            ),
        ]
        result = figure_planner_node(sample_state)

        assert len(result["figure_requests"]) == 3
        assert result["figure_requests"][0]["strategy"] == "mermaid"
        assert result["figure_requests"][1]["strategy"] == "mermaid"
        assert result["figure_requests"][2]["strategy"] == "kling"

    def test_node_skips_non_completed_sections(self, sample_state):
        """Test node only scans completed sections."""
        sample_state["sections"] = [
            SectionContent(
                index=1,
                title="Completed",
                content="% [FIGURE:fig1|architecture|架构|Figure 1]",
                status="completed",
            ),
            SectionContent(
                index=2,
                title="Writing",
                content="% [FIGURE:fig2|flowchart|流程|Figure 2]",
                status="writing",
            ),
            SectionContent(
                index=3,
                title="Pending",
                content="% [FIGURE:fig3|chart|图表|Figure 3]",
                status="pending",
            ),
        ]
        result = figure_planner_node(sample_state)

        # Only fig1 from completed section should be extracted
        assert len(result["figure_requests"]) == 1
        assert result["figure_requests"][0]["id"] == "fig1"

    def test_node_with_chart_type(self, sample_state):
        """Test node correctly handles chart type."""
        sample_state["sections"] = [
            SectionContent(
                index=1,
                title="实验结果",
                content="% [FIGURE:result-chart|chart|实验结果对比|图4：结果对比]",
                status="completed",
            ),
        ]
        result = figure_planner_node(sample_state)

        assert len(result["figure_requests"]) == 1
        assert result["figure_requests"][0]["strategy"] == "python"

    def test_node_with_concept_type(self, sample_state):
        """Test node correctly handles concept type."""
        sample_state["sections"] = [
            SectionContent(
                index=1,
                title="理论基础",
                content="% [FIGURE:theory|concept|理论框架|Figure 5]",
                status="completed",
            ),
        ]
        result = figure_planner_node(sample_state)

        assert len(result["figure_requests"]) == 1
        assert result["figure_requests"][0]["strategy"] == "kling"
