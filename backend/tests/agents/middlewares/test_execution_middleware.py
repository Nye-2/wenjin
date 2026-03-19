"""Tests for ExecutionMiddleware."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.middlewares.execution import ExecutionMiddleware
from src.execution.types import ExecutionResult, ExecutionStatus, ExecutionType


class TestExecutionMiddleware:
    """Tests for ExecutionMiddleware."""

    @pytest.fixture
    def mock_service(self):
        """Create mock execution service."""
        service = Mock()
        service.execute = AsyncMock()
        return service

    @pytest.fixture
    def middleware(self, mock_service):
        """Create ExecutionMiddleware instance."""
        return ExecutionMiddleware(execution_service=mock_service)

    def test_execution_tools_list(self, middleware):
        """Should have list of execution tools."""
        assert "compile_latex_tool" in middleware.EXECUTION_TOOLS
        assert middleware.EXECUTION_TOOLS["compile_latex_tool"] == ExecutionType.LATEX_COMPILE

    @pytest.mark.asyncio
    async def test_skips_non_execution_tools(self, middleware):
        """Should not process non-execution tools."""
        state = {"messages": []}
        config = {"configurable": {}}

        result = await middleware.before_tool(
            state=state,
            config=config,
            tool_name="bash_tool",
            tool_args={"command": "ls"},
        )
        # Returns (tool_name, tool_args) tuple unchanged
        assert result == ("bash_tool", {"command": "ls"})

    @pytest.mark.asyncio
    async def test_processes_compile_latex_tool(self, middleware, mock_service):
        """Should process compile_latex_tool."""
        mock_service.execute.return_value = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            sandbox_path="/mnt/user-data/test.pdf",
            execution_time_ms=1000,
        )

        state = {"messages": []}
        config = {"configurable": {"thread_id": "thread-1", "workspace_id": "ws-1"}}

        # before_tool should process and return modified args
        await middleware.before_tool(
            state=state,
            config=config,
            tool_name="compile_latex_tool",
            tool_args={
                "latex_source": "\\documentclass{article}\\begin{document}test\\end{document}",
            },
        )

        # The result should be stored for after_tool
        assert "execution_result" in config.get("configurable", config)
