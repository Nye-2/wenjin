"""Tests for lead agent tool assembly."""

from __future__ import annotations

from unittest.mock import patch

from src.agents.chat_agent.agent import get_available_tools


class FakeTool:
    """Minimal tool stub for tool assembly tests."""

    def __init__(self, name: str):
        self.name = name


def test_get_available_tools_includes_cached_mcp_tools():
    with patch("src.mcp.get_cached_mcp_tools", return_value=[FakeTool("mcp_search")]):
        tools = get_available_tools(include_mcp=True)

    tool_names = [tool.name for tool in tools]
    assert "mcp_search" in tool_names


def test_get_available_tools_filters_mcp_paper_discovery_tools():
    with patch(
        "src.mcp.get_cached_mcp_tools",
        return_value=[
            FakeTool("mcp_search"),
            FakeTool("arxiv_search"),
            FakeTool("pubmed_search"),
            FakeTool("doi_resolve"),
        ],
    ):
        tools = get_available_tools(include_mcp=True)

    tool_names = {tool.name for tool in tools}
    assert "mcp_search" in tool_names
    assert "arxiv_search" not in tool_names
    assert "pubmed_search" not in tool_names
    assert "doi_resolve" not in tool_names


def test_get_available_tools_can_skip_mcp_tools():
    with patch("src.mcp.get_cached_mcp_tools", return_value=[FakeTool("mcp_search")]):
        tools = get_available_tools(include_mcp=False)

    tool_names = [tool.name for tool in tools]
    assert "mcp_search" not in tool_names


def test_get_available_tools_uses_canonical_runtime_tool_names():
    tools = get_available_tools(include_mcp=False)

    tool_names = {tool.name for tool in tools}
    assert "bash" not in tool_names
    assert "read_file" not in tool_names
    assert "write_file" not in tool_names
    assert "str_replace" not in tool_names
    assert "ls" not in tool_names
    assert "glob" not in tool_names
    assert "grep" not in tool_names
    assert "view_image" in tool_names
    assert "ask_clarification" in tool_names
    assert "present_files" in tool_names
    assert "list_reference_library" in tool_names
    assert "search_reference_text_units" in tool_names
    assert "read_reference_outline_node" in tool_names
    assert "semantic_scholar_search" not in tool_names
    assert "semantic_scholar_search_tool" not in tool_names
    assert "search_external" not in tool_names
    assert "run_workspace_feature" not in tool_names
    assert "task" not in tool_names


def test_get_available_tools_can_include_execution_tools():
    tools = get_available_tools(
        include_mcp=False,
        include_execution=True,
    )

    tool_names = {tool.name for tool in tools}
    assert "compile_latex_tool" in tool_names
