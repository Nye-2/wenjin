"""Tests for sandbox LangChain tools."""

import pytest
from langchain_core.tools import BaseTool

from src.sandbox.tools import (
    bash_tool,
    read_file_tool,
    write_file_tool,
    str_replace_tool,
    list_dir_tool,
    create_sandbox_tools,
)


class TestToolDefinitions:
    """Test that all tools are properly defined."""

    def test_bash_tool_exists(self):
        """Should have bash tool defined."""
        assert bash_tool is not None
        assert bash_tool.name == "bash"

    def test_read_file_tool_exists(self):
        """Should have read_file tool defined."""
        assert read_file_tool is not None
        assert read_file_tool.name == "read_file"

    def test_write_file_tool_exists(self):
        """Should have write_file tool defined."""
        assert write_file_tool is not None
        assert write_file_tool.name == "write_file"

    def test_str_replace_tool_exists(self):
        """Should have str_replace tool defined."""
        assert str_replace_tool is not None
        assert str_replace_tool.name == "str_replace"

    def test_list_dir_tool_exists(self):
        """Should have list_dir tool defined."""
        assert list_dir_tool is not None
        assert list_dir_tool.name == "list_dir"

    def test_bash_tool_description(self):
        """Should have meaningful description."""
        assert "command" in bash_tool.description.lower()

    def test_read_file_tool_description(self):
        """Should have meaningful description."""
        assert "file" in read_file_tool.description.lower()

    def test_write_file_tool_description(self):
        """Should have meaningful description."""
        assert "write" in write_file_tool.description.lower()


class TestCreateSandboxTools:
    """Test the create_sandbox_tools function."""

    def test_returns_list(self):
        """Should return a list of tools."""
        tools = create_sandbox_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_returns_all_tools(self):
        """Should return all required tools."""
        tools = create_sandbox_tools()
        tool_names = [t.name for t in tools]

        assert "bash" in tool_names
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "str_replace" in tool_names
        assert "list_dir" in tool_names

    def test_all_tools_are_base_tools(self):
        """All tools should be LangChain tools."""
        tools = create_sandbox_tools()
        for tool in tools:
            assert isinstance(tool, BaseTool)

    def test_returns_five_tools(self):
        """Should return exactly five tools."""
        tools = create_sandbox_tools()
        assert len(tools) == 5
