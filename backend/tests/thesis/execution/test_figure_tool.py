# tests/thesis/execution/test_figure_tool.py
"""Tests for figure generation tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.thesis.execution.figure_tool import generate_figure, GenerateFigureResult, FigureStrategy
from src.execution.types import ExecutionStatus


class TestGenerateFigure:
    """Tests for generate_figure function."""

    @pytest.mark.asyncio
    async def test_generate_mermaid_diagram(self):
        """Test Mermaid diagram generation."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.SUCCESS
        mock_result.sandbox_path = "/sandbox/test/diagram.pdf"
        mock_result.metadata = {}
        mock_result.error_message = None
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await generate_figure(
            strategy="mermaid",
            content="graph TD\n A --> B",
            execution_service=mock_service,
            workspace_id="ws-001",
        )

        assert result.success is True
        assert result.figure_path == "/sandbox/test/diagram.pdf"
        assert result.strategy == "mermaid"

    @pytest.mark.asyncio
    async def test_generate_python_plot(self):
        """Test Python plot generation."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.SUCCESS
        mock_result.sandbox_path = "/sandbox/test/chart.png"
        mock_result.metadata = {"format": "png"}
        mock_result.error_message = None
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await generate_figure(
            strategy="python",
            content="import matplotlib.pyplot as plt\nplt.plot([1,2,3])\nplt.savefig('chart.png')",
            execution_service=mock_service,
        )

        assert result.success is True
        assert result.figure_path == "/sandbox/test/chart.png"

    @pytest.mark.asyncio
    async def test_generate_ai_image(self):
        """Test AI image generation."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.SUCCESS
        mock_result.sandbox_path = "/sandbox/test/concept.png"
        mock_result.metadata = {"provider": "kling"}
        mock_result.error_message = None
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await generate_figure(
            strategy="kling",
            content="A flowchart showing data processing pipeline",
            execution_service=mock_service,
        )

        assert result.success is True
        assert result.figure_path == "/sandbox/test/concept.png"

    @pytest.mark.asyncio
    async def test_generate_figure_failure(self):
        """Test figure generation failure handling."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.FAILED
        mock_result.error_message = "Invalid Mermaid syntax"
        mock_result.sandbox_path = None
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await generate_figure(
            strategy="mermaid",
            content="invalid mermaid",
            execution_service=mock_service,
        )

        assert result.success is False
        assert "Invalid Mermaid syntax" in result.error

    @pytest.mark.asyncio
    async def test_unknown_strategy_defaults_to_mermaid(self):
        """Test unknown strategy defaults to mermaid."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status = ExecutionStatus.SUCCESS
        mock_result.sandbox_path = "/sandbox/test/default.pdf"
        mock_result.metadata = {}
        mock_result.error_message = None

        async def verify_type(request):
            assert request.execution_type.value == "mermaid_diagram"
            return mock_result

        mock_service.execute = verify_type

        result = await generate_figure(
            strategy="unknown_type",
            content="some content",
            execution_service=mock_service,
        )

        assert result.success is True
