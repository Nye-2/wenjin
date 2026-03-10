"""Tests for sandbox LangChain tools."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.sandbox.providers.local import LocalSandbox
from src.sandbox.tools import (
    bash_tool,
    ls_tool,
    read_file_tool,
    write_file_tool,
    str_replace_tool,
    create_sandbox_tools,
)


class TestSandboxToolDefinitions:
    def test_bash_tool_definition(self):
        """Should have bash tool with correct name."""
        assert bash_tool.name == "bash"
        assert "command" in bash_tool.description.lower()

    def test_ls_tool_definition(self):
        """Should have ls tool with correct name."""
        assert ls_tool.name == "ls"
        assert "directory" in ls_tool.description.lower()

    def test_read_file_tool_definition(self):
        """Should have read_file tool with correct name."""
        assert read_file_tool.name == "read_file"
        assert "file" in read_file_tool.description.lower()

    def test_write_file_tool_definition(self):
        """Should have write_file tool with correct name."""
        assert write_file_tool.name == "write_file"
        assert "write" in write_file_tool.description.lower()

    def test_str_replace_tool_definition(self):
        """Should have str_replace tool with correct name."""
        assert str_replace_tool.name == "str_replace"
        assert "replace" in str_replace_tool.description.lower()


class TestCreateSandboxTools:
    def test_creates_all_tools(self):
        """Should create all sandbox tools."""
        tools = create_sandbox_tools()
        tool_names = [t.name for t in tools]

        assert "bash" in tool_names
        assert "ls" in tool_names
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "str_replace" in tool_names

    def test_returns_five_tools(self):
        """Should return exactly five tools."""
        tools = create_sandbox_tools()
        assert len(tools) == 5
