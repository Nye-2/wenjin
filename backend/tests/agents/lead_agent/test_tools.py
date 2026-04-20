"""Tests for lead agent tool assembly."""

from __future__ import annotations

import builtins
from unittest.mock import ANY, patch

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
    assert "glob" in tool_names
    assert "grep" in tool_names
    assert "view_image" in tool_names
    assert "ask_clarification" in tool_names
    assert "present_files" in tool_names
    assert "list_workspace_literature_toc" in tool_names
    assert "search_workspace_literature" in tool_names
    assert "read_workspace_literature_section" in tool_names
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


def test_get_available_tools_logs_semantic_scholar_import_error():
    original_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "src.academic.tools.semantic_scholar":
            raise ImportError("missing semantic scholar")
        return original_import(name, globals, locals, fromlist, level)

    with patch("src.agents.lead_agent.agent.logger") as mock_logger, patch(
        "builtins.__import__",
        side_effect=_import,
    ):
        tools = get_available_tools(include_mcp=False, subagent_enabled=False)

    tool_names = {tool.name for tool in tools}
    assert "semantic_scholar_search" not in tool_names
    mock_logger.warning.assert_any_call(
        "Semantic Scholar tool unavailable; skipping academic search registration: %s",
        ANY,
    )


def test_get_available_tools_logs_external_search_load_error():
    original_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "src.academic.literature.tools":
            raise RuntimeError("schema failure")
        return original_import(name, globals, locals, fromlist, level)

    with patch("src.agents.lead_agent.agent.logger") as mock_logger, patch(
        "builtins.__import__",
        side_effect=_import,
    ):
        tools = get_available_tools(include_mcp=False, subagent_enabled=False)

    tool_names = {tool.name for tool in tools}
    assert "search_external" not in tool_names
    mock_logger.error.assert_any_call(
        "Failed to load external literature search tool: %s",
        ANY,
    )
