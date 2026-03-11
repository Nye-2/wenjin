# tests/thesis/execution/test_latex_tool.py
"""Tests for LaTeX compilation tool."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.thesis.execution.latex_tool import compile_latex, CompileLatexResult
from src.execution.types import ExecutionStatus


class TestCompileLatex:
    """Tests for compile_latex function."""

    @pytest.mark.asyncio
    async def test_compile_latex_success(self):
        """Test successful LaTeX compilation."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.SUCCESS
        mock_result.sandbox_path = "/sandbox/test/thesis.pdf"
        mock_result.metadata = {"page_count": 10}
        mock_result.error_message = None
        mock_result.logs = "Compilation successful"
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await compile_latex(
            latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
            execution_service=mock_service,
            workspace_id="ws-001",
            thread_id="thread-001",
        )

        assert result.success is True
        assert result.pdf_path == "/sandbox/test/thesis.pdf"
        assert result.page_count == 10

    @pytest.mark.asyncio
    async def test_compile_latex_failure(self):
        """Test LaTeX compilation failure."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.FAILED
        mock_result.sandbox_path = None
        mock_result.error_message = "LaTeX error: Missing $"
        mock_result.logs = "Error log"
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await compile_latex(
            latex_source=r"\documentclass{article}\begin{document}",
            execution_service=mock_service,
            workspace_id="ws-001",
        )

        assert result.success is False
        assert result.error == "LaTeX error: Missing $"

    @pytest.mark.asyncio
    async def test_compile_latex_with_bibliography(self):
        """Test LaTeX compilation with bibliography."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.SUCCESS
        mock_result.sandbox_path = "/sandbox/test/thesis.pdf"
        mock_result.metadata = {}
        mock_result.logs = "Compilation successful"
        mock_service.execute = AsyncMock(return_value=mock_result)

        # Verify the request includes bibliography
        async def verify_request(request):
            assert request.options.get("bibliography") == "@article{test}"
            return mock_result

        mock_service.execute = verify_request

        result = await compile_latex(
            latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
            execution_service=mock_service,
            bibliography="@article{test}",
        )

        assert result.success is True
