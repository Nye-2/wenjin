"""Tests for lead agent tool assembly."""

from __future__ import annotations

from unittest.mock import patch

from src.agents.lead_agent.agent import get_available_tools


class FakeTool:
    """Minimal tool stub for tool assembly tests."""

    def __init__(self, name: str):
        self.name = name


def test_get_available_tools_includes_cached_mcp_tools():
    with patch("src.mcp.get_cached_mcp_tools", return_value=[FakeTool("mcp_search")]):
        tools = get_available_tools(include_mcp=True, subagent_enabled=False)

    tool_names = [tool.name for tool in tools]
    assert "mcp_search" in tool_names


def test_get_available_tools_can_skip_mcp_tools():
    with patch("src.mcp.get_cached_mcp_tools", return_value=[FakeTool("mcp_search")]):
        tools = get_available_tools(include_mcp=False, subagent_enabled=False)

    tool_names = [tool.name for tool in tools]
    assert "mcp_search" not in tool_names


def test_get_available_tools_uses_canonical_runtime_tool_names():
    tools = get_available_tools(include_mcp=False, subagent_enabled=True)

    tool_names = {tool.name for tool in tools}
    assert "bash" in tool_names
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "str_replace" in tool_names
    assert "ls" in tool_names
    assert "view_image" in tool_names
    assert "ask_clarification" in tool_names
    assert "present_files" in tool_names
    assert "run_workspace_feature" in tool_names
    assert "task" in tool_names


def test_get_available_tools_can_include_execution_tools():
    tools = get_available_tools(
        include_mcp=False,
        include_execution=True,
        subagent_enabled=False,
    )

    tool_names = {tool.name for tool in tools}
    assert "compile_latex_tool" in tool_names
