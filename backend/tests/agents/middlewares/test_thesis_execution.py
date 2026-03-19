"""Tests for thesis execution tool integration."""

from src.agents.middlewares.execution import ExecutionMiddleware
from src.execution.types import ExecutionType


def test_execution_tools_includes_latex():
    """Test that compile_latex_tool is in EXECUTION_TOOLS."""
    assert "compile_latex_tool" in ExecutionMiddleware.EXECUTION_TOOLS


def test_execution_type_for_latex():
    """Test that LaTeX compilation maps to correct execution type."""
    exec_type = ExecutionMiddleware.EXECUTION_TOOLS.get("compile_latex_tool")
    assert exec_type == ExecutionType.LATEX_COMPILE
