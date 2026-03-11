# Thesis ExecutionService Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate ExecutionService into thesis workflow nodes to replace stub implementations with real execution.

**Architecture:** Use dependency injection pattern to provide ExecutionService to thesis nodes. Create execution tools that call ExecutionService with proper ExecutionTypes. Update figure_generator and compiler nodes to use the new tools.

**Tech Stack:** Python 3.12, asyncio, DockerExecutionService, pytest

---

## Overview

### Current State
- `figure_generator.py` - Returns placeholder paths
- `compiler.py` - Returns placeholder paths

### Target State
- Both nodes use ExecutionService via tools
- Real PDF generation via LaTeX compilation
- Real figure generation via Mermaid/Python/Kling

### Components to Build

```
src/thesis/
├── execution/
│   ├── __init__.py           # Execution tools for thesis
│   ├── latex_tool.py         # compile_latex_tool wrapper
│   └── figure_tool.py         # generate_figure_tool wrapper
│
└── workflow/
    └── nodes/
        ├── figure_generator.py  # Update to use tool
        └── compiler.py          # Update to use tool
```

---

## Task 1: Create Execution Tool Base Module

**Files:**
- Create: `src/thesis/execution/__init__.py`

**Step 1: Write the module init**

```python
# src/thesis/execution/__init__.py
"""Execution tools for thesis workflow.

This module provides tool wrappers around ExecutionService
for use by thesis workflow nodes.
"""

from .latex_tool import compile_latex, CompileLatexResult
from .figure_tool import generate_figure, GenerateFigureResult

__all__ = [
    "compile_latex",
    "CompileLatexResult",
    "generate_figure",
    "GenerateFigureResult",
]
```

**Step 2: Commit**

```bash
git add src/thesis/execution/__init__.py
git commit -m "feat(thesis): add execution tools module init"
```

---

## Task 2: Create LaTeX Compilation Tool

**Files:**
- Create: `src/thesis/execution/latex_tool.py`
- Create: `tests/thesis/execution/test_latex_tool.py`

**Step 1: Write failing test**

```python
# tests/thesis/execution/test_latex_tool.py
"""Tests for LaTeX compilation tool."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.thesis.execution.latex_tool import compile_latex, CompileLatexResult


class TestCompileLatex:
    """Tests for compile_latex function."""

    @pytest.mark.asyncio
    async def test_compile_latex_success(self):
        """Test successful LaTeX compilation."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.sandbox_path = "/sandbox/test/thesis.pdf"
        mock_result.metadata = {"page_count": 10}
        mock_result.error_message = None
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await compile_latex(
            latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
            execution_service=mock_service,
            workspace_id="ws-001",
            thread_id="thread-001",
        )

        assert result.success is True
        assert result.pdf_path == "/sandbox/test/thesis.pdf"
        assert result.page_count == 10

    @pytest.mark.asyncio
    async def test_compile_latex_failure(self):
        """Test LaTeX compilation failure."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "failed"
        mock_result.sandbox_path = None
        mock_result.error_message = "LaTeX error: Missing $"
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await compile_latex(
            latex_source=r"\documentclass{article}\begin{document}",
            execution_service=mock_service,
            workspace_id="ws-001",
        )

        assert result.success is False
        assert result.error == "LaTeX error: Missing $"

    @pytest.mark.asyncio
    async def test_compile_latex_with_bibliography(self):
        """Test LaTeX compilation with bibliography."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.sandbox_path = "/sandbox/test/thesis.pdf"
        mock_result.metadata = {}
        mock_service.execute = AsyncMock(return_value=mock_result)

        # Verify the request includes bibliography
        async def verify_request(request):
            assert request.options.get("bibliography") == "@article{test}"
            return mock_result

        mock_service.execute = verify_request

        result = await compile_latex(
            latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
            execution_service=mock_service,
            bibliography="@article{test}",
        )

        assert result.success is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/thesis/execution/test_latex_tool.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement latex_tool.py**

```python
# src/thesis/execution/latex_tool.py
"""LaTeX compilation tool for thesis workflow.

Provides async interface to ExecutionService for LaTeX compilation.
"""

import logging
from dataclasses import dataclass
from typing import Any

from src.execution.types import ExecutionType, ExecutionRequest, ExecutionStatus
from src.thesis.config import thesis_settings

from src.thesis.execution import get_execution_service

logger = logging.getLogger(__name__)


@dataclass
class CompileLatexResult:
    """Result of LaTeX compilation.

    Attributes:
        success: Whether compilation succeeded
        pdf_path: Path to generated PDF (sandbox path)
        page_count: Number of pages in the PDF
        error: Error message if compilation failed
        logs: Compilation logs
    """
    success: bool
    pdf_path: str | None = None
    page_count: int | None = None
    error: str | None = None
    logs: str | None = None


async def compile_latex(
    latex_source: str,
    execution_service: Any = None,
    workspace_id: str | None = None,
    thread_id: str | None = None,
    bibliography: str | None = None,
    compiler: str | None = None,
    bibliography_style: str | None = None,
    timeout: int = 120,
) -> CompileLatexResult:
    """Compile LaTeX source to PDF using ExecutionService.

    Args:
        latex_source: LaTeX document content
        execution_service: ExecutionService instance (uses global if None)
        workspace_id: Workspace ID for sandbox path
        thread_id: Thread ID for tracking
        bibliography: BibTeX content (optional)
        compiler: LaTeX compiler (default from thesis_settings)
        bibliography_style: BibTeX style (default from thesis_settings)
        timeout: Compilation timeout in seconds

    Returns:
        CompileLatexResult with success status and PDF path or error
    """
    if execution_service is None:
        execution_service = get_execution_service()

    # Use config defaults
    if compiler is None:
        compiler = thesis_settings.latex_compiler
    if bibliography_style is None:
        bibliography_style = thesis_settings.bibliography_style

    # Build execution request
    request = ExecutionRequest(
        execution_type=ExecutionType.LATEX_COMPILE,
        content=latex_source,
        options={
            "compiler": compiler,
            "bibliography": bibliography,
            "bibliography_style": bibliography_style,
        },
        timeout=timeout,
        workspace_id=workspace_id,
        thread_id=thread_id,
    )

    logger.info(f"Compiling LaTeX for workspace={workspace_id}, compiler={compiler}")

    try:
        result = await execution_service.execute(request)

        if result.status == ExecutionStatus.SUCCESS:
            logger.info(f"LaTeX compilation succeeded: {result.sandbox_path}")
            return CompileLatexResult(
                success=True,
                pdf_path=result.sandbox_path,
                page_count=result.metadata.get("page_count"),
                logs=result.logs,
            )
        else:
            error_msg = result.error_message or f"Compilation failed with status: {result.status}"
            logger.error(f"LaTeX compilation failed: {error_msg}")
            return CompileLatexResult(
                success=False,
                error=error_msg,
                logs=result.logs,
            )

    except Exception as e:
        logger.exception(f"LaTeX compilation error: {e}")
        return CompileLatexResult(
            success=False,
            error=str(e),
        )


__all__ = ["compile_latex", "CompileLatexResult"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/thesis/execution/test_latex_tool.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/thesis/execution/latex_tool.py tests/thesis/execution/test_latex_tool.py
git commit -m "feat(thesis): add LaTeX compilation tool with ExecutionService integration"
```

---

## Task 3: Create Figure Generation Tool

**Files:**
- Create: `src/thesis/execution/figure_tool.py`
- Create: `tests/thesis/execution/test_figure_tool.py`

**Step 1: Write failing test**

```python
# tests/thesis/execution/test_figure_tool.py
"""Tests for figure generation tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.thesis.execution.figure_tool import generate_figure, GenerateFigureResult, FigureStrategy


class TestGenerateFigure:
    """Tests for generate_figure function."""

    @pytest.mark.asyncio
    async def test_generate_mermaid_diagram(self):
        """Test Mermaid diagram generation."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.sandbox_path = "/sandbox/test/diagram.pdf"
        mock_result.metadata = {}
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await generate_figure(
            strategy="mermaid",
            content="graph TD\n A --> B",
            execution_service=mock_service,
            workspace_id="ws-001",
        )

        assert result.success is True
        assert result.figure_path == "/sandbox/test/diagram.pdf"
        assert result.strategy == "mermaid"

    @pytest.mark.asyncio
    async def test_generate_python_plot(self):
        """Test Python plot generation."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.sandbox_path = "/sandbox/test/chart.png"
        mock_result.metadata = {"format": "png"}
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await generate_figure(
            strategy="python",
            content="import matplotlib.pyplot as plt\nplt.plot([1,2,3])\nplt.savefig('chart.png')",
            execution_service=mock_service,
        )

        assert result.success is True
        assert result.figure_path == "/sandbox/test/chart.png"

    @pytest.mark.asyncio
    async def test_generate_ai_image(self):
        """Test AI image generation."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.sandbox_path = "/sandbox/test/concept.png"
        mock_result.metadata = {"provider": "kling"}
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await generate_figure(
            strategy="kling",
            content="A flowchart showing data processing pipeline",
            execution_service=mock_service,
        )

        assert result.success is True
        assert result.figure_path == "/sandbox/test/concept.png"

    @pytest.mark.asyncio
    async def test_generate_figure_failure(self):
        """Test figure generation failure handling."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "failed"
        mock_result.error_message = "Invalid Mermaid syntax"
        mock_service.execute = AsyncMock(return_value=mock_result)

        result = await generate_figure(
            strategy="mermaid",
            content="invalid mermaid",
            execution_service=mock_service,
        )

        assert result.success is False
        assert "Invalid Mermaid syntax" in result.error

    @pytest.mark.asyncio
    async def test_unknown_strategy_defaults_to_mermaid(self):
        """Test unknown strategy defaults to mermaid."""
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.status.value = "success"
        mock_result.sandbox_path = "/sandbox/test/default.pdf"

        async def verify_type(request):
            assert request.execution_type.value == "mermaid_diagram"
            return mock_result

        mock_service.execute = verify_type

        result = await generate_figure(
            strategy="unknown_type",
            content="some content",
            execution_service=mock_service,
        )

        assert result.success is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/thesis/execution/test_figure_tool.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement figure_tool.py**

```python
# src/thesis/execution/figure_tool.py
"""Figure generation tool for thesis workflow.

Provides async interface to ExecutionService for figure generation.
Supports three strategies: mermaid, python, kling.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.execution.types import ExecutionType, ExecutionRequest, ExecutionStatus

from src.thesis.execution import get_execution_service

logger = logging.getLogger(__name__)


class FigureStrategy(str, Enum):
    """Figure generation strategy."""
    MERMAID = "mermaid"
    PYTHON = "python"
    KLING = "kling"


# Map strategy to ExecutionType
STRATEGY_TO_EXECUTION_TYPE = {
    FigureStrategy.MERMAID: ExecutionType.MERMAID_DIAGRAM,
    FigureStrategy.PYTHON: ExecutionType.PYTHON_PLOT,
    FigureStrategy.KLING: ExecutionType.AI_IMAGE,
    "mermaid": ExecutionType.MERMAID_DIAGRAM,
    "python": ExecutionType.PYTHON_PLOT,
    "kling": ExecutionType.AI_IMAGE,
}


@dataclass
class GenerateFigureResult:
    """Result of figure generation.

    Attributes:
        success: Whether generation succeeded
        figure_path: Path to generated figure (sandbox path)
        strategy: Strategy used for generation
        format: Figure format (pdf, png, svg)
        error: Error message if generation failed
    """
    success: bool
    figure_path: str | None = None
    strategy: str = ""
    format: str | None = None
    error: str | None = None


async def generate_figure(
    strategy: str,
    content: str,
    execution_service: Any = None,
    workspace_id: str | None = None,
    thread_id: str | None = None,
    figure_id: str | None = None,
    timeout: int = 60,
) -> GenerateFigureResult:
    """Generate a figure using ExecutionService.

    Args:
        strategy: Generation strategy ("mermaid", "python", "kling")
        content: Content for generation (Mermaid code, Python code, or AI prompt)
        execution_service: ExecutionService instance (uses global if None)
        workspace_id: Workspace ID for sandbox path
        thread_id: Thread ID for tracking
        figure_id: Optional figure ID for filename
        timeout: Generation timeout in seconds

    Returns:
        GenerateFigureResult with success status and figure path or error
    """
    if execution_service is None:
        execution_service = get_execution_service()

    # Map strategy to execution type (default to mermaid)
    exec_type = STRATEGY_TO_EXECUTION_TYPE.get(strategy, ExecutionType.MERMAID_DIAGRAM)

    # Build execution request
    request = ExecutionRequest(
        execution_type=exec_type,
        content=content,
        options={
            "figure_id": figure_id,
        },
        timeout=timeout,
        workspace_id=workspace_id,
        thread_id=thread_id,
        output_filename=f"{figure_id}.pdf" if figure_id else None,
    )

    logger.info(f"Generating figure with strategy={strategy}, workspace={workspace_id}")

    try:
        result = await execution_service.execute(request)

        if result.status == ExecutionStatus.SUCCESS:
            logger.info(f"Figure generation succeeded: {result.sandbox_path}")
            return GenerateFigureResult(
                success=True,
                figure_path=result.sandbox_path,
                strategy=strategy,
                format=result.metadata.get("format", "pdf"),
            )
        else:
            error_msg = result.error_message or f"Generation failed with status: {result.status}"
            logger.error(f"Figure generation failed: {error_msg}")
            return GenerateFigureResult(
                success=False,
                strategy=strategy,
                error=error_msg,
            )

    except Exception as e:
        logger.exception(f"Figure generation error: {e}")
        return GenerateFigureResult(
            success=False,
            strategy=strategy,
            error=str(e),
        )


__all__ = ["generate_figure", "GenerateFigureResult", "FigureStrategy"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/thesis/execution/test_figure_tool.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/thesis/execution/figure_tool.py tests/thesis/execution/test_figure_tool.py
git commit -m "feat(thesis): add figure generation tool with multi-strategy support"
```

---

## Task 4: Create Execution Service Getter

**Files:**
- Modify: `src/thesis/execution/__init__.py`

**Step 1: Add get_execution_service function**

```python
# Add to src/thesis/execution/__init__.py

_execution_service: Any = None


def get_execution_service() -> Any:
    """Get the global ExecutionService instance.

    In production, this should be injected via dependency injection.
    For now, creates a new instance on first call.

    Returns:
        ExecutionService instance
    """
    global _execution_service
    if _execution_service is None:
        from src.execution.service import DockerExecutionService
        import os
        sandbox_dir = os.environ.get("SANDBOX_DIR", "/tmp/academiagpt-sandbox")
        _execution_service = DockerExecutionService(sandbox_base_dir=sandbox_dir)
    return _execution_service


def set_execution_service(service: Any) -> None:
    """Set the global ExecutionService instance (for testing)."""
    global _execution_service
    _execution_service = service
```

**Step 2: Commit**

```bash
git add src/thesis/execution/__init__.py
git commit -m "feat(thesis): add execution service getter with DI support"
```

---

## Task 5: Update Compiler Node

**Files:**
- Modify: `src/thesis/workflow/nodes/compiler.py`
- Create: `tests/thesis/workflow/nodes/test_compiler_integration.py`

**Step 1: Write integration test**

```python
# tests/thesis/workflow/nodes/test_compiler_integration.py
"""Integration tests for compiler node with ExecutionService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.thesis.workflow.nodes.compiler import compile_latex_node
from src.thesis.workflow.state import ThesisWorkflowState


@pytest.fixture
def mock_execution_service():
    """Create mock execution service."""
    service = MagicMock()
    result = MagicMock()
    result.status.value = "success"
    result.sandbox_path = "/sandbox/test-workflow/thesis.pdf"
    result.metadata = {"page_count": 15}
    service.execute = AsyncMock(return_value=result)
    return service


@pytest.fixture
def state_with_latex() -> ThesisWorkflowState:
    """Create state with final LaTeX content."""
    return {
        "workspace_id": "ws-compiler-test",
        "thread_id": "thread-001",
        "paper_title": "Test Thesis",
        "discipline": "计算机科学",
        "abstract_content": "Test abstract",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "final_latex": r"\documentclass{article}\begin{document}Test\end{document}",
        "bib_content": "@article{test, title={Test}}",
        "current_phase": "assembly",
        "progress": 0.95,
        "errors": [],
    }


@pytest.mark.asyncio
async def test_compiler_uses_execution_service(mock_execution_service, state_with_latex):
    """Test compiler node calls ExecutionService."""
    with patch("src.thesis.execution.latex_tool.get_execution_service", return_value=mock_execution_service):
        result = await compile_latex_node(state_with_latex)

        assert result["pdf_path"] == "/sandbox/test-workflow/thesis.pdf"
        assert result["current_phase"] == "compile"
        assert result["progress"] == 1.0
        # Verify ExecutionService was called
        mock_execution_service.execute.assert_called_once()


@pytest.mark.asyncio
async def test_compiler_handles_execution_failure(state_with_latex):
    """Test compiler handles ExecutionService failure."""
    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.status.value = "failed"
    mock_result.error_message = "LaTeX compilation error"
    mock_service.execute = AsyncMock(return_value=mock_result)

    with patch("src.thesis.execution.latex_tool.get_execution_service", return_value=mock_service):
        result = await compile_latex_node(state_with_latex)

        assert "errors" in result
        assert len(result["errors"]) > 0
        assert "LaTeX compilation error" in result["errors"][0]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/thesis/workflow/nodes/test_compiler_integration.py -v`
Expected: FAIL (node returns stub path, not calling ExecutionService)

**Step 3: Update compiler.py**

```python
# src/thesis/workflow/nodes/compiler.py
"""LaTeX compiler node for thesis workflow.

This node compiles the final LaTeX document to PDF using ExecutionService.
"""

import logging
from typing import Any

from src.thesis.config import thesis_settings
from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.execution.latex_tool import compile_latex
from .base import log_node_start, log_node_end

logger = logging.getLogger(__name__)


async def compile_latex_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Compile LaTeX document to PDF using ExecutionService.

    This node integrates with ExecutionService for actual LaTeX compilation.
    It handles compilation errors gracefully and returns the PDF path.

    Args:
        state: Current workflow state containing final_latex

    Returns:
        State updates with pdf_path on success, or error message on failure
    """
    log_node_start("compiler", state)

    workspace_id = state.get("workspace_id", "unknown")
    thread_id = state.get("thread_id")
    final_latex = state.get("final_latex")
    bib_content = state.get("bib_content")

    # Check if final_latex exists
    if not final_latex:
        error_msg = "Cannot compile: final_latex not found in state"
        logger.error(f"[Thesis:{workspace_id}] {error_msg}")

        return {
            "errors": [error_msg],
            "current_phase": "compile",
            "progress": 0.95,
        }

    logger.info(
        f"[Thesis:{workspace_id}] Compiling LaTeX with "
        f"compiler={thesis_settings.latex_compiler}, "
        f"bibliography_style={thesis_settings.bibliography_style}"
    )

    # Call ExecutionService via tool
    result = await compile_latex(
        latex_source=final_latex,
        bibliography=bib_content,
        compiler=thesis_settings.latex_compiler,
        bibliography_style=thesis_settings.bibliography_style,
        workspace_id=workspace_id,
        thread_id=thread_id,
        timeout=180,  # 3 minutes for large documents
    )

    if result.success:
        logger.info(f"[Thesis:{workspace_id}] Compilation succeeded: {result.pdf_path}")
        log_node_end("compiler", state, {"pdf_path": result.pdf_path})

        return {
            "pdf_path": result.pdf_path,
            "current_phase": "compile",
            "progress": 1.0,
        }
    else:
        error_msg = f"LaTeX compilation failed: {result.error}"
        logger.error(f"[Thesis:{workspace_id}] {error_msg}")

        return {
            "errors": [error_msg],
            "current_phase": "compile",
            "progress": 0.95,
        }


__all__ = ["compile_latex_node"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/thesis/workflow/nodes/test_compiler_integration.py -v`
Expected: 2 passed

**Step 5: Run all compiler tests**

Run: `pytest tests/thesis/workflow/nodes/test_compiler*.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/thesis/workflow/nodes/compiler.py tests/thesis/workflow/nodes/test_compiler_integration.py
git commit -m "feat(thesis): integrate ExecutionService into compiler node"
```

---

## Task 6: Update Figure Generator Node

**Files:**
- Modify: `src/thesis/workflow/nodes/figure_generator.py`
- Create: `tests/thesis/workflow/nodes/test_figure_generator_integration.py`

**Step 1: Write integration test**

```python
# tests/thesis/workflow/nodes/test_figure_generator_integration.py
"""Integration tests for figure generator node with ExecutionService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.thesis.workflow.nodes.figure_generator import figure_generator_node
from src.thesis.workflow.state import ThesisWorkflowState


@pytest.fixture
def mock_execution_service():
    """Create mock execution service for figures."""
    service = MagicMock()

    async def mock_execute(request):
        result = MagicMock()
        result.status.value = "success"
        # Return different paths based on execution type
        if "mermaid" in str(request.execution_type):
            result.sandbox_path = "/sandbox/figures/diagram.pdf"
            result.metadata = {"format": "pdf"}
        elif "python" in str(request.execution_type):
            result.sandbox_path = "/sandbox/figures/chart.png"
            result.metadata = {"format": "png"}
        else:
            result.sandbox_path = "/sandbox/figures/concept.png"
            result.metadata = {"format": "png"}
        return result

    service.execute = mock_execute
    return service


@pytest.fixture
def state_with_figure_requests() -> ThesisWorkflowState:
    """Create state with figure requests."""
    return {
        "workspace_id": "ws-figure-test",
        "thread_id": "thread-001",
        "paper_title": "Test Thesis",
        "discipline": "计算机科学",
        "abstract_content": "",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [
            {
                "id": "fig1",
                "section_index": 1,
                "figure_type": "architecture",
                "description": "System architecture diagram",
                "caption": "Figure 1: System Architecture",
                "strategy": "mermaid",
            },
            {
                "id": "fig2",
                "section_index": 2,
                "figure_type": "chart",
                "description": "Performance comparison",
                "caption": "Figure 2: Performance",
                "strategy": "python",
            },
            {
                "id": "fig3",
                "section_index": 3,
                "figure_type": "concept",
                "description": "AI-generated concept illustration",
                "caption": "Figure 3: Concept",
                "strategy": "kling",
            },
        ],
        "generated_figures": [],
        "current_phase": "figure_planning",
        "progress": 0.82,
        "errors": [],
    }


@pytest.mark.asyncio
async def test_figure_generator_uses_execution_service(mock_execution_service, state_with_figure_requests):
    """Test figure generator calls ExecutionService for each strategy."""
    with patch("src.thesis.execution.figure_tool.get_execution_service", return_value=mock_execution_service):
        result = await figure_generator_node(state_with_figure_requests)

        assert "generated_figures" in result
        assert len(result["generated_figures"]) == 3

        # Check each figure was generated with correct strategy
        figures = result["generated_figures"]
        assert figures[0]["strategy"] == "mermaid"
        assert figures[1]["strategy"] == "python"
        assert figures[2]["strategy"] == "kling"


@pytest.mark.asyncio
async def test_figure_generator_handles_failure(state_with_figure_requests):
    """Test figure generator handles ExecutionService failure gracefully."""
    mock_service = MagicMock()
    mock_result = MagicMock()
    mock_result.status.value = "failed"
    mock_result.error_message = "Generation failed"
    mock_service.execute = AsyncMock(return_value=mock_result)

    with patch("src.thesis.execution.figure_tool.get_execution_service", return_value=mock_service):
        result = await figure_generator_node(state_with_figure_requests)

        # Should still generate figures, but with error info
        assert len(result["generated_figures"]) == 3
        # Figures should indicate failure
        for fig in result["generated_figures"]:
            assert "error" in fig or fig.get("file_path") is None


@pytest.mark.asyncio
async def test_figure_generator_empty_requests():
    """Test figure generator with no requests."""
    state: ThesisWorkflowState = {
        "workspace_id": "ws-empty",
        "thread_id": "thread-001",
        "paper_title": "Test",
        "discipline": "计算机科学",
        "abstract_content": "",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "figure_planning",
        "progress": 0.82,
        "errors": [],
    }

    result = await figure_generator_node(state)

    assert result["generated_figures"] == []
    assert result["progress"] == 0.88
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/thesis/workflow/nodes/test_figure_generator_integration.py -v`
Expected: FAIL (node returns stub paths)

**Step 3: Update figure_generator.py**

```python
# src/thesis/workflow/nodes/figure_generator.py
"""Figure generator node for thesis workflow.

This node generates figures based on figure_requests using ExecutionService.
Supports three strategies: mermaid (diagrams), python (plots), kling (AI images).
"""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.execution.figure_tool import generate_figure
from .base import log_node_start, log_node_end, get_attr

logger = logging.getLogger(__name__)


async def figure_generator_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Generate figures using ExecutionService.

    This node integrates with ExecutionService for actual figure generation:
    - mermaid: Mermaid diagrams via MERMAID_DIAGRAM
    - python: Data plots via PYTHON_PLOT
    - kling: AI images via AI_IMAGE

    Args:
        state: Current workflow state with figure_requests

    Returns:
        State updates with generated_figures list
    """
    log_node_start("figure_generator", state)

    workspace_id = state.get("workspace_id", "unknown")
    thread_id = state.get("thread_id")
    figure_requests = state.get("figure_requests", [])
    generated_figures = []

    for request in figure_requests:
        figure_id = get_attr(request, "id", "unknown")
        strategy = get_attr(request, "strategy", "mermaid")
        description = get_attr(request, "description", "")
        caption = get_attr(request, "caption", "")

        logger.info(f"[Thesis:{workspace_id}] Generating figure {figure_id} with strategy={strategy}")

        # Call ExecutionService via tool
        result = await generate_figure(
            strategy=strategy,
            content=description,  # For kling, this is the prompt; for others, it's code
            workspace_id=workspace_id,
            thread_id=thread_id,
            figure_id=figure_id,
            timeout=60,
        )

        if result.success:
            generated_figures.append({
                "id": figure_id,
                "request_id": figure_id,
                "file_path": result.figure_path,
                "latex_ref": f"\\includegraphics[width=0.8\\textwidth]{{{figure_id}.{result.format or 'pdf'}}}",
                "strategy": strategy,
                "format": result.format,
            })
            logger.info(f"[Thesis:{workspace_id}] Figure {figure_id} generated: {result.figure_path}")
        else:
            # Store error but continue with other figures
            generated_figures.append({
                "id": figure_id,
                "request_id": figure_id,
                "file_path": None,
                "error": result.error,
                "strategy": strategy,
            })
            logger.error(f"[Thesis:{workspace_id}] Figure {figure_id} failed: {result.error}")

    progress = 0.85 if figure_requests else 0.88
    log_node_end("figure_generator", state, {"progress": progress})

    return {
        "generated_figures": generated_figures,
        "current_phase": "figure_generation",
        "progress": progress,
    }


__all__ = ["figure_generator_node"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/thesis/workflow/nodes/test_figure_generator_integration.py -v`
Expected: 3 passed

**Step 5: Run all figure generator tests**

Run: `pytest tests/thesis/workflow/nodes/test_figure_generator*.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/thesis/workflow/nodes/figure_generator.py tests/thesis/workflow/nodes/test_figure_generator_integration.py
git commit -m "feat(thesis): integrate ExecutionService into figure generator node"
```

---

## Task 7: Final Verification

**Step 1: Run all thesis tests**

Run: `pytest tests/thesis/ -v`
Expected: All tests pass

**Step 2: Run integration tests**

Run: `pytest tests/thesis/ -v -k "integration"`
Expected: Integration tests pass

**Step 3: Update handover document**

Add to `docs/plans/2026-03-11-thesis-handover.md`:

```markdown
### 3.5 ExecutionService Integration Status (2026-03-11)

**Completed:**
- `src/thesis/execution/latex_tool.py` - LaTeX compilation via ExecutionService
- `src/thesis/execution/figure_tool.py` - Figure generation with multi-strategy support
- `compiler.py` - Full ExecutionService integration
- `figure_generator.py` - Full ExecutionService integration

**Providers Required:**
- LaTeXProvider (Docker) - ✅ Implemented
- MermaidProvider - ⚠️ Needs implementation
- PythonPlotProvider - ⚠️ Needs implementation
- AIImageProvider (Kling) - ⚠️ Needs implementation

**Next Steps:**
- Implement missing providers in `src/execution/providers/`
- Add provider registration to ExecutionService.PROVIDER_MAP
```

**Step 4: Commit**

```bash
git add docs/plans/2026-03-11-thesis-handover.md
git commit -m "docs(thesis): update handover with ExecutionService integration status"
```

---

## Summary

| Task | Files Created | Files Modified | Tests |
|------|---------------|-----------------|-------|
| 1. Module Init | `execution/__init__.py` | - | 0 |
| 2. LaTeX Tool | `execution/latex_tool.py` | - | 3 |
| 3. Figure Tool | `execution/figure_tool.py` | - | 5 |
| 4. Service Getter | - | `execution/__init__.py` | 0 |
| 5. Compiler Node | - | `nodes/compiler.py` | 2 |
| 6. Figure Generator | - | `nodes/figure_generator.py` | 3 |
| 7. Verification | - | `handover.md` | - |

**Total:** 2 new source files, 2 modified source files, ~13 new tests
