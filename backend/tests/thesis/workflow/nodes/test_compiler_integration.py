# tests/thesis/workflow/nodes/test_compiler_integration.py
"""Integration tests for compiler node with ExecutionService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.execution.types import ExecutionStatus
from src.thesis.workflow.nodes.compiler import compile_latex_node
from src.thesis.workflow.state import ThesisWorkflowState


@pytest.fixture
def mock_execution_service():
    """Create mock execution service."""
    service = MagicMock()
    result = MagicMock()
    result.status = ExecutionStatus.SUCCESS
    result.sandbox_path = "/sandbox/test-workflow/thesis.pdf"
    result.metadata = {"page_count": 15}
    result.error_message = None
    result.logs = "Compilation successful"
    service.execute = AsyncMock(return_value=result)
    return service


@pytest.fixture
def state_with_latex() -> ThesisWorkflowState:
    """Create state with final LaTeX content."""
    return {
        "workspace_id": "ws-compiler-test",
        "thread_id": "thread-001",
        "paper_title": "Test Thesis",
        "discipline": "计算机科学",
        "abstract_content": "Test abstract",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "final_latex": r"\documentclass{article}\begin{document}Test\end{document}",
        "bib_content": "@article{test, title={Test}}",
        "current_phase": "assembly",
        "progress": 0.95,
        "errors": [],
    }


@pytest.mark.asyncio
async def test_compiler_uses_execution_service(mock_execution_service, state_with_latex):
    """Test compiler node calls ExecutionService."""
    with patch("src.thesis.execution.latex_tool.get_execution_service", return_value=mock_execution_service):
        result = await compile_latex_node(state_with_latex)

        assert result["pdf_path"] == "/sandbox/test-workflow/thesis.pdf"
        assert result["current_phase"] == "compile"
        assert result["progress"] == 1.0
        # Verify ExecutionService was called
        mock_execution_service.execute.assert_called_once()


@pytest.mark.asyncio
async def test_compiler_handles_execution_failure(state_with_latex):
    """Test compiler handles ExecutionService failure."""
    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.status = ExecutionStatus.FAILED
    mock_result.error_message = "LaTeX compilation error"
    mock_result.logs = "! Emergency stop."
    mock_service.execute = AsyncMock(return_value=mock_result)

    with patch("src.thesis.execution.latex_tool.get_execution_service", return_value=mock_service):
        result = await compile_latex_node(state_with_latex)

        assert "errors" in result
        assert len(result["errors"]) > 0
        assert "LaTeX compilation error" in result["errors"][0]
