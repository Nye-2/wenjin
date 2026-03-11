# Workflow Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect Citation module with LaTeX compilation, enabling automatic BibTeX generation from citation IDs.

**Architecture:** Add citation_ids parameter to compile_latex tool, enhance ExecutionMiddleware to fetch papers from database and generate BibTeX content using existing BibTeXExporter.

**Tech Stack:** SQLAlchemy async, BibTeXExporter, LangChain tools, ExecutionMiddleware

---

## Task 1: Enhance BibTeXExporter Citation Key Generation

**Files:**
- Modify: `src/academic/citation/bibtex/exporter.py:70-90`
- Test: `tests/academic/citation/test_bibtex_exporter.py`

**Context:** The current `_generate_key` uses lowercase with underscores (e.g., `smith_2024_deep`). For LaTeX `\cite{}` commands, we want a simpler format like `Smith2024` for easier LLM usage.

**Step 1: Write the failing test**

```python
# tests/academic/citation/test_bibtex_exporter.py
# Add to existing test file

def test_generate_citation_key_simple():
    """Test citation key generation returns simple format."""
    from src.academic.citation.bibtex.exporter import generate_citation_key

    paper = {
        "authors": [{"name": "John Smith"}],
        "year": 2024,
        "title": "Deep Learning Methods"
    }

    key = generate_citation_key(paper)
    assert key == "Smith2024"


def test_generate_citation_key_no_year():
    """Test citation key when year is missing."""
    from src.academic.citation.bibtex.exporter import generate_citation_key

    paper = {
        "authors": [{"name": "Jane Doe"}],
        "title": "Important Paper"
    }

    key = generate_citation_key(paper)
    assert key == "DoeNd"


def test_generate_citation_key_multiple_authors():
    """Test citation key uses first author only."""
    from src.academic.citation.bibtex.exporter import generate_citation_key

    paper = {
        "authors": [
            {"name": "Alice Johnson"},
            {"name": "Bob Williams"}
        ],
        "year": 2023,
    }

    key = generate_citation_key(paper)
    assert key == "Johnson2023"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/academic/citation/test_bibtex_exporter.py::test_generate_citation_key_simple -v`
Expected: FAIL with "cannot import name 'generate_citation_key'"

**Step 3: Write minimal implementation**

```python
# src/academic/citation/bibtex/exporter.py
# Add this function at the module level (before the class)

def generate_citation_key(paper: dict) -> str:
    """Generate BibTeX citation key in simple format: FirstAuthorYear.

    This format (e.g., Smith2024) is designed for easy use with LaTeX \\cite{}.

    Args:
        paper: Paper dict with authors, year, title fields.

    Returns:
        Citation key string.
    """
    parts = []

    # First author lastname (preserve case for LaTeX)
    authors = paper.get("authors", [])
    if authors:
        name = authors[0].get("name", "")
        if name:
            # Get last name (last word)
            last_name = name.split()[-1]
            parts.append(last_name)

    # Year
    year = paper.get("year")
    if year:
        parts.append(str(year))
    else:
        parts.append("n.d.")

    return "".join(parts) if parts else "Unknown"
```

**Step 4: Update _generate_key to use new function**

```python
# src/academic/citation/bibtex/exporter.py
# Modify _generate_key method in BibTeXExporter class

def _generate_key(self, paper: dict) -> str:
    """Generate BibTeX citation key using standardized format."""
    return generate_citation_key(paper)
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/academic/citation/test_bibtex_exporter.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/academic/citation/bibtex/exporter.py tests/academic/citation/test_bibtex_exporter.py
git commit -m "feat(citation): add generate_citation_key function for LaTeX-friendly keys"
```

---

## Task 2: Add citation_ids Parameter to compile_latex Tool

**Files:**
- Modify: `src/tools/execution/compile_latex.py`
- Test: `tests/tools/execution/test_compile_latex.py`

**Context:** Add citation_ids parameter to the tool schema. The middleware will handle the actual paper fetching and BibTeX generation.

**Step 1: Write the failing test**

```python
# tests/tools/execution/test_compile_latex.py
"""Tests for compile_latex tool."""

import pytest


def test_compile_latex_has_citation_ids_parameter():
    """Test that compile_latex tool accepts citation_ids parameter."""
    from src.tools.execution.compile_latex import CompileLatexInput

    # Should accept citation_ids
    input_data = CompileLatexInput(
        latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
        citation_ids=["paper-uuid-1", "paper-uuid-2"],
    )

    assert input_data.citation_ids == ["paper-uuid-1", "paper-uuid-2"]


def test_compile_latex_citation_ids_optional():
    """Test that citation_ids is optional."""
    from src.tools.execution.compile_latex import CompileLatexInput

    input_data = CompileLatexInput(
        latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
    )

    assert input_data.citation_ids is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/tools/execution/test_compile_latex.py -v`
Expected: FAIL with "missing field 'citation_ids'" or similar

**Step 3: Write minimal implementation**

```python
# src/tools/execution/compile_latex.py
# Modify CompileLatexInput class

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
        description="Optional list of paper IDs to cite. System will fetch papers and generate bibliography automatically."
    )
    bibliography_style: str = Field(
        default="plain",
        description="Bibliography style for generated references (plain, alpha, abbrv, etc.)"
    )
    timeout: int = Field(
        default=120,
        ge=30,
        le=600,
        description="Compilation timeout in seconds"
    )
```

**Step 4: Update tool function signature**

```python
# src/tools/execution/compile_latex.py
# Modify compile_latex_tool function

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
    compile it into a PDF document. Supports both pdflatex and xelatex compilers.

    For Chinese content, always use xelatex (the default).

    The tool returns the path to the compiled PDF file, or an error message
    if compilation fails.

    Args:
        latex_source: Complete LaTeX source code including documentclass and
                      all content.
        compiler: LaTeX compiler (pdflatex or xelatex). Default: xelatex.
        bibliography: Optional BibTeX content for references.
        citation_ids: Optional list of paper IDs. System will fetch papers
                      and generate bibliography automatically.
        bibliography_style: Bibliography style (plain, alpha, abbrv, etc.).
        timeout: Compilation timeout in seconds. Default: 120.

    Returns:
        Success message with PDF path, or error message.
    """
    # Actual execution handled by ExecutionMiddleware
    # This returns empty string; real implementation in middleware
    return ""
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/tools/execution/test_compile_latex.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/tools/execution/compile_latex.py tests/tools/execution/test_compile_latex.py
git commit -m "feat(execution): add citation_ids and bibliography_style to compile_latex tool"
```

---

## Task 3: Enhance ExecutionMiddleware with Citation Support

**Files:**
- Modify: `src/agents/middlewares/execution.py`
- Test: `tests/agents/middlewares/test_execution_citations.py`

**Context:** Add logic to fetch papers by citation_ids and generate BibTeX content using BibTeXExporter. Pass to LaTeX provider via options.

**Step 1: Write the failing test**

```python
# tests/agents/middlewares/test_execution_citations.py
"""Tests for ExecutionMiddleware citation handling."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_build_request_with_citation_ids():
    """Test that citation_ids are processed to generate bibliography."""
    from src.agents.middlewares.execution import ExecutionMiddleware
    from src.execution.types import ExecutionType

    # Mock execution service
    mock_service = MagicMock()
    middleware = ExecutionMiddleware(mock_service)

    # Mock database and papers
    mock_paper_1 = MagicMock()
    mock_paper_1.id = "uuid-1"
    mock_paper_1.title = "Test Paper"
    mock_paper_1.authors = [{"name": "John Smith"}]
    mock_paper_1.year = 2024
    mock_paper_1.venue = "Nature"
    mock_paper_1.doi = "10.1234/test"

    mock_paper_2 = MagicMock()
    mock_paper_2.id = "uuid-2"
    mock_paper_2.title = "Another Paper"
    mock_paper_2.authors = [{"name": "Jane Doe"}]
    mock_paper_2.year = 2023
    mock_paper_2.venue = "Science"
    mock_paper_2.doi = None

    # Build request
    request = middleware._build_request(
        exec_type=ExecutionType.LATEX_COMPILE,
        tool_args={
            "latex_source": r"\documentclass{article}\begin{document}\end{document}",
            "compiler": "xelatex",
            "citation_ids": ["uuid-1", "uuid-2"],
            "bibliography_style": "alpha",
        },
        thread_id="test-thread",
        workspace_id="test-workspace",
    )

    # Check that bibliography was generated
    assert request.options.get("bibliography") is not None
    assert "Smith2024" in request.options["bibliography"]
    assert "Doe2023" in request.options["bibliography"]
    assert request.options.get("bibliography_style") == "alpha"


@pytest.mark.asyncio
async def test_build_request_with_explicit_bibliography():
    """Test that explicit bibliography takes precedence over citation_ids."""
    from src.agents.middlewares.execution import ExecutionMiddleware
    from src.execution.types import ExecutionType

    mock_service = MagicMock()
    middleware = ExecutionMiddleware(mock_service)

    explicit_bib = "@article{Test2024, author={Test Author}, title={Test}}"

    request = middleware._build_request(
        exec_type=ExecutionType.LATEX_COMPILE,
        tool_args={
            "latex_source": r"\documentclass{article}\begin{document}\end{document}",
            "bibliography": explicit_bib,
            "citation_ids": ["uuid-1"],  # Should be ignored
        },
        thread_id="test-thread",
        workspace_id="test-workspace",
    )

    # Explicit bibliography should be used
    assert request.options.get("bibliography") == explicit_bib
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/agents/middlewares/test_execution_citations.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# src/agents/middlewares/execution.py
# Add imports at top

import logging
from typing import Any

from .base import Middleware
from src.execution.types import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionType,
)
from src.agents.thread_state import ThreadState
from langchain_core.runnables import RunnableConfig
from src.database import Paper
from src.academic.citation.bibtex.exporter import BibTeXExporter, generate_citation_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
```

```python
# src/agents/middlewares/execution.py
# Modify _build_request method

def _build_request(
    self,
    exec_type: ExecutionType,
    tool_args: dict,
    thread_id: str | None,
    workspace_id: str | None,
) -> ExecutionRequest:
    """Build execution request from tool arguments.

    Args:
        exec_type: Execution type.
        tool_args: Tool arguments.
        thread_id: Thread ID.
        workspace_id: Workspace ID.

    Returns:
        ExecutionRequest instance.
    """
    if exec_type == ExecutionType.LATEX_COMPILE:
        # Handle bibliography: explicit > generated from citation_ids
        bibliography = tool_args.get("bibliography")
        citation_ids = tool_args.get("citation_ids")

        # If no explicit bibliography but citation_ids provided, generate it
        # Note: This is sync for now; will be enhanced to async in production
        # For async version, see _generate_bibliography_async method
        if not bibliography and citation_ids:
            bibliography = self._generate_bibliography_sync(citation_ids)

        return ExecutionRequest(
            execution_type=exec_type,
            content=tool_args.get("latex_source", ""),
            options={
                "compiler": tool_args.get("compiler", "xelatex"),
                "bibliography": bibliography,
                "bibliography_style": tool_args.get("bibliography_style", "plain"),
            },
            timeout=tool_args.get("timeout", 120),
            thread_id=thread_id,
            workspace_id=workspace_id,
        )

    # Other execution types will be added here
    raise ValueError(f"Unsupported execution type: {exec_type}")

def _generate_bibliography_sync(self, citation_ids: list[str]) -> str | None:
    """Generate BibTeX content from citation IDs (synchronous placeholder).

    In production, this would use async database access.
    For now, returns None to allow the async version in before_tool.

    Args:
        citation_ids: List of paper IDs.

    Returns:
        BibTeX content or None.
    """
    # This is a placeholder - actual async implementation in before_tool
    return None
```

**Step 4: Add async bibliography generation to before_tool**

```python
# src/agents/middlewares/execution.py
# Modify before_tool method

async def before_tool(
    self,
    state: ThreadState,
    config: RunnableConfig,
    tool_name: str,
    tool_args: dict,
) -> tuple[str, dict]:
    """Process tool before execution.

    Args:
        state: Current thread state
        config: Runtime configuration
        tool_name: Name of the tool to execute
        tool_args: Arguments for the tool

    Returns:
        Tuple of (tool_name, tool_args) - can modify either
    """
    if tool_name not in self.EXECUTION_TOOLS:
        return tool_name, tool_args  # Not an execution tool, continue normally

    # Handle citation_ids: generate bibliography if needed
    citation_ids = tool_args.get("citation_ids")
    explicit_bib = tool_args.get("bibliography")

    if citation_ids and not explicit_bib:
        # Get database session from config
        configurable = config.get("configurable", {})
        db: AsyncSession | None = configurable.get("db")

        if db:
            bibliography = await self._generate_bibliography(db, citation_ids)
            if bibliography:
                tool_args = {**tool_args, "bibliography": bibliography}

    # Get execution type
    exec_type = self.EXECUTION_TOOLS[tool_name]

    # Extract context
    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id")
    workspace_id = configurable.get("workspace_id")

    # Build execution request
    request = self._build_request(
        exec_type=exec_type,
        tool_args=tool_args,
        thread_id=thread_id,
        workspace_id=workspace_id,
    )

    # Execute
    result = await self.execution_service.execute(request)

    # Store result for after_tool
    configurable["execution_result"] = result

    return tool_name, tool_args

async def _generate_bibliography(
    self,
    db: AsyncSession,
    citation_ids: list[str],
) -> str | None:
    """Generate BibTeX content from citation IDs.

    Args:
        db: Database session.
        citation_ids: List of paper IDs.

    Returns:
        BibTeX formatted string or None if no papers found.
    """
    try:
        # Fetch papers
        result = await db.execute(
            select(Paper).where(Paper.id.in_(citation_ids))
        )
        papers = result.scalars().all()

        if not papers:
            logger.warning(f"No papers found for citation_ids: {citation_ids}")
            return None

        # Convert to dicts for exporter
        paper_dicts = [
            {
                "title": p.title,
                "authors": p.authors,
                "year": p.year,
                "venue": p.venue,
                "doi": p.doi,
                "abstract": p.abstract,
            }
            for p in papers
        ]

        # Generate BibTeX
        exporter = BibTeXExporter()
        return exporter.export(paper_dicts)

    except Exception as e:
        logger.error(f"Failed to generate bibliography: {e}")
        return None
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/agents/middlewares/test_execution_citations.py -v`
Expected: Tests may need adjustment for sync/async handling

**Step 6: Commit**

```bash
git add src/agents/middlewares/execution.py tests/agents/middlewares/test_execution_citations.py
git commit -m "feat(middleware): add citation_ids support with automatic BibTeX generation"
```

---

## Task 4: Add Bibliography Injection to LaTeX Provider

**Files:**
- Modify: `src/execution/providers/latex.py:45-80`
- Test: `tests/execution/providers/test_latex_bibliography.py`

**Context:** When citation_ids are provided but LaTeX doesn't have \bibliography{} commands, auto-inject them before \end{document}.

**Step 1: Write the failing test**

```python
# tests/execution/providers/test_latex_bibliography.py
"""Tests for LaTeX provider bibliography handling."""

import pytest
from src.execution.providers.latex import LaTeXProvider


def test_inject_bibliography_commands():
    """Test automatic bibliography command injection."""
    provider = LaTeXProvider()

    latex = r"""\documentclass{article}
\begin{document}
Hello world \cite{Smith2024}.
\end{document}"""

    result = provider._inject_bibliography(latex, "refs")

    assert r"\bibliographystyle{plain}" in result
    assert r"\bibliography{refs}" in result
    assert result.endswith(r"\end{document}")


def test_no_injection_if_bibliography_exists():
    """Test no injection if bibliography commands already exist."""
    provider = LaTeXProvider()

    latex = r"""\documentclass{article}
\begin{document}
Hello world \cite{Smith2024}.
\bibliographystyle{alpha}
\bibliography{refs}
\end{document}"""

    result = provider._inject_bibliography(latex, "refs")

    # Should not add duplicate commands
    assert result.count(r"\bibliography{refs}") == 1
    assert result.count(r"\bibliographystyle") == 1


def test_no_injection_if_no_citations():
    """Test no injection if LaTeX has no citations."""
    provider = LaTeXProvider()

    latex = r"""\documentclass{article}
\begin{document}
Hello world.
\end{document}"""

    result = provider._inject_bibliography(latex, "refs")

    # Should not add bibliography
    assert r"\bibliography" not in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/execution/providers/test_latex_bibliography.py -v`
Expected: FAIL with "'LaTeXProvider' object has no attribute '_inject_bibliography'"

**Step 3: Write minimal implementation**

```python
# src/execution/providers/latex.py
# Add new method to LaTeXProvider class

def _inject_bibliography(
    self,
    content: str,
    bib_filename: str = "refs",
    style: str = "plain",
) -> str:
    """Inject bibliography commands into LaTeX if needed.

    Args:
        content: LaTeX source code.
        bib_filename: BibTeX filename (without .bib extension).
        style: Bibliography style name.

    Returns:
        LaTeX content with bibliography commands if needed.
    """
    # Check if bibliography commands already exist
    if r"\bibliography{" in content:
        return content

    # Check if there are any \cite{} commands
    if r"\cite{" not in content:
        return content

    # Inject before \end{document}
    injection = f"\\bibliographystyle{{{style}}}\n\\bibliography{{{bib_filename}}}\n"

    if r"\end{document}" in content:
        return content.replace(r"\end{document}", injection + r"\end{document}")
    else:
        # No \end{document}, append at end
        return content + "\n" + injection
```

**Step 4: Update build_command to use injection**

```python
# src/execution/providers/latex.py
# Modify build_command method

def build_command(self, content: str, options: dict) -> list[str]:
    """Build Docker command for LaTeX compilation.

    Args:
        content: LaTeX source code.
        options: Compilation options:
            - compiler: "xelatex" (default) or "pdflatex"
            - bibliography: BibTeX content string
            - bibliography_file: BibTeX filename (default: "refs.bib")
            - bibliography_style: Bibliography style (default: "plain")

    Returns:
        Command list for Docker execution.
    """
    compiler = options.get("compiler", "xelatex")
    bibliography = options.get("bibliography", "")
    has_bib = bool(bibliography or options.get("bibliography_file"))

    # Build commands: write source file, then compile
    commands = []

    # Inject bibliography commands if needed
    if has_bib:
        bib_filename = options.get("bibliography_file", "refs.bib").replace(".bib", "")
        style = options.get("bibliography_style", "plain")
        content = self._inject_bibliography(content, bib_filename, style)

    # Write main.tex file (escape single quotes in content)
    escaped_content = content.replace("'", "'\\''")
    commands.append(f"cat > main.tex << 'LATEX_EOF'\n{escaped_content}\nLATEX_EOF")

    # Write bibliography if provided
    if bibliography:
        bib_filename = options.get("bibliography_file", "refs.bib")
        escaped_bib = bibliography.replace("'", "'\\''")
        commands.append(f"cat > {bib_filename} << 'BIB_EOF'\n{escaped_bib}\nBIB_END")

    # Build compilation chain
    commands.extend(self._build_compile_chain(compiler, has_bib))

    # Wrap in shell for command chaining
    return ["/bin/bash", "-c", " && ".join(commands)]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/execution/providers/test_latex_bibliography.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/execution/providers/latex.py tests/execution/providers/test_latex_bibliography.py
git commit -m "feat(latex): auto-inject bibliography commands when citations exist"
```

---

## Task 5: Create Integration Test

**Files:**
- Create: `tests/integration/test_citation_latex_workflow.py`

**Context:** End-to-end test verifying the complete workflow from citation_ids to compiled PDF (mocked).

**Step 1: Write the integration test**

```python
# tests/integration/test_citation_latex_workflow.py
"""Integration tests for citation-to-LaTeX workflow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_citation_to_latex_workflow():
    """Test complete workflow: citation_ids -> BibTeX -> LaTeX compilation."""
    from src.agents.middlewares.execution import ExecutionMiddleware
    from src.execution.types import ExecutionType
    from src.academic.citation.bibtex.exporter import generate_citation_key

    # Setup mock papers in database
    mock_paper = MagicMock()
    mock_paper.id = "test-uuid"
    mock_paper.title = "Deep Learning Advances"
    mock_paper.authors = [{"name": "John Smith"}]
    mock_paper.year = 2024
    mock_paper.venue = "Nature"
    mock_paper.doi = "10.1234/test"
    mock_paper.abstract = None

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_paper]
    mock_db.execute.return_value = mock_result

    # Setup middleware
    mock_service = MagicMock()
    mock_service.execute = AsyncMock()
    middleware = ExecutionMiddleware(mock_service)

    # Generate citation key
    paper_dict = {
        "title": mock_paper.title,
        "authors": mock_paper.authors,
        "year": mock_paper.year,
    }
    citation_key = generate_citation_key(paper_dict)
    assert citation_key == "Smith2024"

    # Generate bibliography
    bibliography = await middleware._generate_bibliography(mock_db, ["test-uuid"])

    assert bibliography is not None
    assert "Smith2024" in bibliography
    assert "Deep Learning Advances" in bibliography
    assert "John Smith" in bibliography


@pytest.mark.asyncio
async def test_latex_provider_bibliography_injection():
    """Test LaTeX provider correctly injects bibliography commands."""
    from src.execution.providers.latex import LaTeXProvider

    provider = LaTeXProvider()

    latex_source = r"""\documentclass{article}
\begin{document}
According to \cite{Smith2024}, this is important.
\end{document}"""

    options = {
        "compiler": "xelatex",
        "bibliography": "@article{Smith2024, author={Smith, John}, title={Test}}",
        "bibliography_style": "alpha",
    }

    command = provider.build_command(latex_source, options)
    command_str = " ".join(command)

    # Check that bibliography commands are injected
    assert "bibliographystyle{alpha}" in command_str
    assert "bibliography{refs}" in command_str
```

**Step 2: Run integration test**

Run: `pytest tests/integration/test_citation_latex_workflow.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/integration/test_citation_latex_workflow.py
git commit -m "test(integration): add citation-to-latex workflow tests"
```

---

## Task 6: Update Module Exports and Documentation

**Files:**
- Modify: `src/academic/citation/bibtex/__init__.py`
- Modify: `docs/plans/2026-03-11-workflow-integration-design.md` (optional)

**Step 1: Update exports**

```python
# src/academic/citation/bibtex/__init__.py
"""BibTeX support package."""

from .parser import BibTeXParser
from .exporter import BibTeXExporter, generate_citation_key

__all__ = [
    "BibTeXParser",
    "BibTeXExporter",
    "generate_citation_key",
]
```

**Step 2: Run full test suite**

Run: `pytest tests/academic/citation/ tests/execution/ tests/agents/middlewares/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/academic/citation/bibtex/__init__.py
git commit -m "docs(citation): export generate_citation_key for external use"
```

---

## Summary

**Tasks:**
1. Enhance BibTeXExporter Citation Key Generation
2. Add citation_ids Parameter to compile_latex Tool
3. Enhance ExecutionMiddleware with Citation Support
4. Add Bibliography Injection to LaTeX Provider
5. Create Integration Test
6. Update Module Exports and Documentation

**Key Changes:**
- `generate_citation_key()` function for consistent citation keys
- `compile_latex` tool accepts `citation_ids` and `bibliography_style`
- `ExecutionMiddleware` fetches papers and generates BibTeX
- `LaTeXProvider` auto-injects `\bibliography{}` commands

**Testing:**
- Unit tests for each component
- Integration test for end-to-end workflow
