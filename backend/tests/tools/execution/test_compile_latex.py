"""Tests for compile_latex tool."""

import pytest
from langchain_core.tools import Tool
from src.tools.execution.compile_latex import compile_latex_tool


class TestCompileLatexTool:
    """Tests for compile_latex tool."""

    def test_tool_is_langchain_tool(self):
        """Should be a LangChain tool."""
        from langchain_core.tools import BaseTool
        assert isinstance(compile_latex_tool, BaseTool)

    def test_tool_name(self):
        """Should have correct name."""
        assert compile_latex_tool.name == "compile_latex_tool"

    def test_tool_description(self):
        """Should have descriptive docstring."""
        assert "LaTeX" in compile_latex_tool.description
        assert "PDF" in compile_latex_tool.description

    def test_tool_has_args_schema(self):
        """Should have args schema."""
        assert compile_latex_tool.args_schema is not None

    def test_args_schema_fields(self):
        """Args schema should have expected fields."""
        schema = compile_latex_tool.args_schema.model_json_schema()
        properties = schema.get("properties", {})

        assert "latex_source" in properties
        assert "compiler" in properties
        assert "bibliography" in properties

    def test_compiler_default_is_xelatex(self):
        """Default compiler should be xelatex."""
        schema = compile_latex_tool.args_schema.model_json_schema()
        compiler = schema["properties"]["compiler"]
        assert compiler.get("default") == "xelatex"
