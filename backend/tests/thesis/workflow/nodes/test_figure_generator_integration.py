# tests/thesis/workflow/nodes/test_figure_generator_integration.py
"""Integration tests for figure generator node with ExecutionService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.thesis.workflow.nodes.figure_generator import figure_generator_node
from src.thesis.workflow.state import ThesisWorkflowState
from src.execution.types import ExecutionStatus


@pytest.fixture
def mock_execution_service():
    """Create mock execution service for figures."""
    service = MagicMock()

    async def mock_execute(request):
        result = MagicMock()
        result.status = ExecutionStatus.SUCCESS
        # Return different paths based on execution type
        if "mermaid" in str(request.execution_type):
            result.sandbox_path = "/sandbox/figures/diagram.pdf"
            result.metadata = {"format": "pdf"}
        elif "python" in str(request.execution_type):
            result.sandbox_path = "/sandbox/figures/chart.png"
            result.metadata = {"format": "png"}
        else:
            result.sandbox_path = "/sandbox/figures/concept.png"
            result.metadata = {"format": "png"}
        return result

    service.execute = mock_execute
    return service


@pytest.fixture
def state_with_figure_requests() -> ThesisWorkflowState:
    """Create state with figure requests."""
    return {
        "workspace_id": "ws-figure-test",
        "thread_id": "thread-001",
        "paper_title": "Test Thesis",
        "discipline": "计算机科学",
        "abstract_content": "",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [
            {
                "id": "fig1",
                "section_index": 1,
                "figure_type": "architecture",
                "description": "System architecture diagram",
                "caption": "Figure 1: System Architecture",
                "strategy": "mermaid",
            },
            {
                "id": "fig2",
                "section_index": 2,
                "figure_type": "chart",
                "description": "Performance comparison",
                "caption": "Figure 2: Performance",
                "strategy": "python",
            },
            {
                "id": "fig3",
                "section_index": 3,
                "figure_type": "concept",
                "description": "AI-generated concept illustration",
                "caption": "Figure 3: Concept",
                "strategy": "kling",
            },
        ],
        "generated_figures": [],
        "current_phase": "figure_planning",
        "progress": 0.82,
        "errors": [],
    }


@pytest.mark.asyncio
async def test_figure_generator_uses_execution_service(mock_execution_service, state_with_figure_requests):
    """Test figure generator calls ExecutionService for each strategy."""
    with patch("src.thesis.execution.figure_tool.get_execution_service", return_value=mock_execution_service):
        result = await figure_generator_node(state_with_figure_requests)

        assert "generated_figures" in result
        assert len(result["generated_figures"]) == 3

        # Check each figure was generated with correct strategy
        figures = result["generated_figures"]
        assert figures[0]["strategy"] == "mermaid"
        assert figures[1]["strategy"] == "python"
        assert figures[2]["strategy"] == "kling"


@pytest.mark.asyncio
async def test_figure_generator_handles_failure(state_with_figure_requests):
    """Test figure generator handles ExecutionService failure gracefully."""
    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.status = ExecutionStatus.FAILED
    mock_result.error_message = "Generation failed"
    mock_service.execute = AsyncMock(return_value=mock_result)

    with patch("src.thesis.execution.figure_tool.get_execution_service", return_value=mock_service):
        result = await figure_generator_node(state_with_figure_requests)

        # Should still generate figures, but with error info
        assert len(result["generated_figures"]) == 3
        # Figures should indicate failure
        for fig in result["generated_figures"]:
            assert "error" in fig or fig.get("file_path") is None


@pytest.mark.asyncio
async def test_figure_generator_empty_requests():
    """Test figure generator with no requests."""
    state: ThesisWorkflowState = {
        "workspace_id": "ws-empty",
        "thread_id": "thread-001",
        "paper_title": "Test",
        "discipline": "计算机科学",
        "abstract_content": "",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "figure_planning",
        "progress": 0.82,
        "errors": [],
    }

    result = await figure_generator_node(state)

    assert result["generated_figures"] == []
    assert result["progress"] == 0.88
