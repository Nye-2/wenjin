"""Tests for compile_latex tool."""

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

    def test_compile_latex_has_citation_ids_parameter(self):
        """Test that compile_latex tool accepts citation_ids parameter."""
        from src.tools.execution.compile_latex import CompileLatexInput

        # Should accept citation_ids
        input_data = CompileLatexInput(
            latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
            citation_ids=["paper-uuid-1", "paper-uuid-2"],
        )

        assert input_data.citation_ids == ["paper-uuid-1", "paper-uuid-2"]

    def test_compile_latex_citation_ids_optional(self):
        """Test that citation_ids is optional."""
        from src.tools.execution.compile_latex import CompileLatexInput

        input_data = CompileLatexInput(
            latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
        )

        assert input_data.citation_ids is None

    def test_compile_latex_bibliography_style_default(self):
        """Test that bibliography_style has default value."""
        from src.tools.execution.compile_latex import CompileLatexInput

        input_data = CompileLatexInput(
            latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
        )

        assert input_data.bibliography_style == "plain"
