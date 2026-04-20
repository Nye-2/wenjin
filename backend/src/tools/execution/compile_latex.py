"""LaTeX compilation tool."""

from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class CompileLatexInput(BaseModel):
    """Input schema for compile_latex tool."""

    latex_source: str = Field(
        description="Complete LaTeX source code to compile into PDF"
    )
    compiler: Literal["pdflatex", "xelatex"] = Field(
        default="xelatex",
        description="LaTeX compiler to use. Use xelatex for Chinese or multilingual content."
    )
    bibliography: str | None = Field(
        default=None,
        description="Optional BibTeX bibliography content for references"
    )
    citation_ids: list[str] | None = Field(
        default=None,
        description="Optional list of paper IDs to cite. Used to fetch citation data from the citation service."
    )
    bibliography_style: str = Field(
        default="plain",
        description="Bibliography style for formatting references (e.g., plain, alpha, abbrv, ieee)"
    )
    timeout: int = Field(
        default=120,
        ge=30,
        le=600,
        description="Compilation timeout in seconds"
    )


@tool(args_schema=CompileLatexInput)
async def compile_latex_tool(
    latex_source: str,
    compiler: str = "xelatex",
    bibliography: str | None = None,
    citation_ids: list[str] | None = None,
    bibliography_style: str = "plain",
    timeout: int = 120,
) -> str:
    """Compile LaTeX source code to PDF.

    Use this tool when you have generated complete LaTeX code and need to
    compile it into a PDF document.

    For Chinese content, always use xelatex (the default).

    The tool returns the path to the compiled PDF file, or an error message
    if compilation fails.

    Args:
        latex_source: Complete LaTeX source code including documentclass and
                      all content.
        compiler: LaTeX compiler. Default: xelatex.
        bibliography: Optional BibTeX content for references.
        citation_ids: Optional list of paper IDs to cite. Used to fetch
                      citation data from the citation service.
        bibliography_style: Bibliography style for formatting references.
                           Default: plain.
        timeout: Compilation timeout in seconds. Default: 120.

    Returns:
        Success message with PDF path, or error message.
    """
    # Actual execution handled by ExecutionMiddleware
    # This returns empty string; real implementation in middleware
    return ""


# Export tool instance
compile_latex = compile_latex_tool
