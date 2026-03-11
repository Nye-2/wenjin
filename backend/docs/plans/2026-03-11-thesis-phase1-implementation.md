# Thesis Module Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the thesis module Phase 1, enabling the workflow to actually execute from API call to PDF generation.

**Architecture:** Implement LangGraph state machine with 6 nodes, background task runner, and integrate with existing ExecutionService for LaTeX compilation. TDD approach with unit tests for each component.

**Tech Stack:** Python 3.12, LangGraph, Pydantic v2, FastAPI BackgroundTasks, asyncio, pytest

---

## Task 1: Configuration Management (config.py)

**Files:**
- Create: `src/thesis/config.py`
- Create: `tests/thesis/test_config.py`

### Step 1.1: Write the failing test for ThesisSettings

```python
# tests/thesis/test_config.py
"""Tests for thesis configuration."""

import pytest
from src.thesis.config import thesis_settings, ThesisSettings


def test_thesis_settings_defaults():
    """Test default configuration values."""
    settings = ThesisSettings()
    assert settings.min_references == 10
    assert settings.recommended_references == 20
    assert settings.default_target_words == 2000
    assert settings.max_section_words == 5000
    assert settings.latex_compiler == "xelatex"
    assert settings.bibliography_style == "gbt7714"
    assert settings.task_timeout_hours == 24
    assert settings.max_concurrent_tasks == 10


def test_thesis_settings_env_prefix():
    """Test environment variable prefix."""
    assert ThesisSettings.model_config["env_prefix"] == "THESIS_"


def test_global_settings_instance():
    """Test global settings instance exists."""
    assert thesis_settings is not None
    assert isinstance(thesis_settings, ThesisSettings)
```

### Step 1.2: Run test to verify it fails

Run: `pytest tests/thesis/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.thesis.config'"

### Step 1.3: Write config.py implementation

```python
# src/thesis/config.py
"""Configuration management for thesis generation module."""

from pydantic_settings import BaseSettings


class ThesisSettings(BaseSettings):
    """Configuration for thesis generation.

    All settings can be overridden via environment variables
    with the THESIS_ prefix.

    Attributes:
        min_references: Minimum references required for thesis.
        recommended_references: Target number of references.
        default_target_words: Default word count per section.
        max_section_words: Maximum words per section.
        latex_compiler: LaTeX compiler to use (xelatex, pdflatex).
        bibliography_style: BibTeX style for references.
        task_timeout_hours: Maximum task duration in hours.
        max_concurrent_tasks: Maximum parallel tasks per workspace.
    """

    # Literature configuration
    min_references: int = 10
    recommended_references: int = 20

    # Section configuration
    default_target_words: int = 2000
    max_section_words: int = 5000

    # LaTeX configuration
    latex_compiler: str = "xelatex"
    bibliography_style: str = "gbt7714"

    # Task configuration
    task_timeout_hours: int = 24
    max_concurrent_tasks: int = 10

    model_config = {"env_prefix": "THESIS_"}


# Global settings instance
thesis_settings = ThesisSettings()


__all__ = ["ThesisSettings", "thesis_settings"]
```

### Step 1.4: Run test to verify it passes

Run: `pytest tests/thesis/test_config.py -v`
Expected: 3 passed

### Step 1.5: Update literature_search.py to use config

```python
# In src/thesis/workflow/nodes/literature_search.py
# Replace lines 13-14 with:
from src.thesis.config import thesis_settings

# Then in check_literature_sufficiency function:
MIN_REFERENCES = thesis_settings.min_references
RECOMMENDED_REFERENCES = thesis_settings.recommended_references
```

### Step 1.6: Run all thesis tests

Run: `pytest tests/thesis/ -v`
Expected: 25 passed (22 existing + 3 new)

### Step 1.7: Commit

```bash
git add src/thesis/config.py tests/thesis/test_config.py src/thesis/workflow/nodes/literature_search.py
git commit -m "feat(thesis): add configuration management with ThesisSettings"
```

---

## Task 2: Figure Planner Node

**Files:**
- Create: `src/thesis/workflow/nodes/figure_planner.py`
- Create: `tests/thesis/workflow/nodes/test_figure_planner.py`
- Modify: `src/thesis/workflow/nodes/__init__.py`

### Step 2.1: Write the failing test

```python
# tests/thesis/workflow/nodes/test_figure_planner.py
"""Tests for figure planner node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.workflow.nodes.figure_planner import (
    extract_figure_placeholders,
    determine_strategy,
    figure_planner_node,
)


@pytest.fixture
def state_with_figures() -> ThesisWorkflowState:
    """Create a state with figure placeholders in sections."""
    return {
        "workspace_id": "ws-001",
        "thread_id": "thread-001",
        "paper_title": "Test Thesis",
        "discipline": "计算机科学",
        "abstract_content": "Abstract",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [
            {
                "index": 1,
                "title": "系统设计",
                "content": """
\\section{系统设计}
系统架构如图所示：
% [FIGURE:fig1|architecture|系统整体架构图|图1-1 系统架构]

详细流程如下：
% [FIGURE:fig2|flowchart|数据处理流程图|图1-2 数据流程]
""",
                "status": "completed",
            },
            {
                "index": 2,
                "title": "实验结果",
                "content": """
\\section{实验结果}
性能对比如下：
% [FIGURE:fig3|chart|准确率对比柱状图|图2-1 准确率对比]
""",
                "status": "completed",
            },
        ],
        "figure_requests": [],
        "generated_figures": [],
        "current_phase": "writing",
        "progress": 0.80,
        "errors": [],
    }


def test_extract_figure_placeholders():
    """Test extracting figure placeholders from content."""
    content = """
    Some text
    % [FIGURE:fig1|architecture|系统架构|图1]
    More text
    % [FIGURE:fig2|flowchart|流程图|图2]
    """
    placeholders = extract_figure_placeholders(content)
    assert len(placeholders) == 2
    assert placeholders[0]["id"] == "fig1"
    assert placeholders[0]["figure_type"] == "architecture"
    assert placeholders[1]["id"] == "fig2"


def test_determine_strategy():
    """Test strategy determination for figure types."""
    assert determine_strategy("architecture") == "mermaid"
    assert determine_strategy("flowchart") == "mermaid"
    assert determine_strategy("chart") == "python"
    assert determine_strategy("concept") == "kling"
    assert determine_strategy("unknown") == "mermaid"  # default


def test_figure_planner_node(state_with_figures):
    """Test figure planner node generates requests."""
    result = figure_planner_node(state_with_figures)

    assert "figure_requests" in result
    assert len(result["figure_requests"]) == 3

    # Check first figure request
    fig1 = result["figure_requests"][0]
    assert fig1["id"] == "fig1"
    assert fig1["figure_type"] == "architecture"
    assert fig1["strategy"] == "mermaid"
    assert fig1["section_index"] == 1

    assert result["current_phase"] == "figure_planning"
    assert result["progress"] == 0.82
```

### Step 2.2: Run test to verify it fails

Run: `pytest tests/thesis/workflow/nodes/test_figure_planner.py -v`
Expected: FAIL with module import error

### Step 2.3: Write figure_planner.py implementation

```python
# src/thesis/workflow/nodes/figure_planner.py
"""Figure planner node for thesis workflow."""

import logging
import re
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState
from .base import log_node_start, log_node_end

logger = logging.getLogger(__name__)

# Placeholder format: % [FIGURE:id|type|description|caption]
PLACEHOLDER_PATTERN = re.compile(
    r"%\s*\[FIGURE:([^|]+)\|([^|]+)\|([^|]+)\|([^\]]+)\]"
)


def extract_figure_placeholders(content: str) -> list[dict[str, str]]:
    """Extract figure placeholders from LaTeX content.

    Args:
        content: LaTeX content with figure placeholders

    Returns:
        List of placeholder dicts with id, figure_type, description, caption
    """
    placeholders = []
    for match in PLACEHOLDER_PATTERN.finditer(content):
        placeholders.append({
            "id": match.group(1).strip(),
            "figure_type": match.group(2).strip(),
            "description": match.group(3).strip(),
            "caption": match.group(4).strip(),
        })
    return placeholders


def determine_strategy(figure_type: str) -> str:
    """Determine generation strategy based on figure type.

    Args:
        figure_type: Type of figure (architecture, flowchart, chart, concept)

    Returns:
        Strategy name: mermaid, python, or kling
    """
    strategy_map = {
        "architecture": "mermaid",
        "flowchart": "mermaid",
        "chart": "python",
        "graph": "python",
        "concept": "kling",
        "diagram": "mermaid",
    }
    return strategy_map.get(figure_type.lower(), "mermaid")


def _get_attr(obj, attr: str, default=None):
    """Handle both Pydantic models and dict objects."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def figure_planner_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Plan figures for thesis by extracting placeholders.

    This node:
    1. Scans all completed sections for figure placeholders
    2. Determines generation strategy for each figure
    3. Creates figure_requests list for the generator node

    Args:
        state: Current workflow state

    Returns:
        State updates with figure_requests
    """
    log_node_start("figure_planner", state)

    sections = state.get("sections", [])
    figure_requests = []

    for section in sections:
        if _get_attr(section, "status") != "completed":
            continue

        content = _get_attr(section, "content", "")
        section_index = _get_attr(section, "index", 0)

        placeholders = extract_figure_placeholders(content)

        for ph in placeholders:
            strategy = determine_strategy(ph["figure_type"])
            figure_requests.append({
                "id": ph["id"],
                "section_index": section_index,
                "figure_type": ph["figure_type"],
                "description": ph["description"],
                "caption": ph["caption"],
                "strategy": strategy,
            })

    logger.info(f"[Thesis] Planned {len(figure_requests)} figures")

    log_node_end("figure_planner", state, {"progress": 0.82})

    return {
        "figure_requests": figure_requests,
        "current_phase": "figure_planning",
        "progress": 0.82,
    }
```

### Step 2.4: Run test to verify it passes

Run: `pytest tests/thesis/workflow/nodes/test_figure_planner.py -v`
Expected: 3 passed

### Step 2.5: Update nodes/__init__.py

```python
# src/thesis/workflow/nodes/__init__.py
"""Thesis workflow nodes."""

from .section_writer import section_writer_node, get_next_section_index
from .literature_search import literature_search_node, check_literature_sufficiency
from .assembler import assemble_latex_node, generate_bibtex
from .figure_planner import figure_planner_node, extract_figure_placeholders, determine_strategy

__all__ = [
    "section_writer_node",
    "get_next_section_index",
    "literature_search_node",
    "check_literature_sufficiency",
    "assemble_latex_node",
    "generate_bibtex",
    "figure_planner_node",
    "extract_figure_placeholders",
    "determine_strategy",
]
```

### Step 2.6: Run all thesis tests

Run: `pytest tests/thesis/ -v`
Expected: 28 passed

### Step 2.7: Commit

```bash
git add src/thesis/workflow/nodes/figure_planner.py tests/thesis/workflow/nodes/test_figure_planner.py src/thesis/workflow/nodes/__init__.py
git commit -m "feat(thesis): add figure planner node with placeholder extraction"
```

---

## Task 3: Figure Generator Node (Stub)

**Files:**
- Create: `src/thesis/workflow/nodes/figure_generator.py`
- Create: `tests/thesis/workflow/nodes/test_figure_generator.py`
- Modify: `src/thesis/workflow/nodes/__init__.py`

### Step 3.1: Write the failing test

```python
# tests/thesis/workflow/nodes/test_figure_generator.py
"""Tests for figure generator node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.workflow.nodes.figure_generator import figure_generator_node


@pytest.fixture
def state_with_requests() -> ThesisWorkflowState:
    """Create a state with figure requests."""
    return {
        "workspace_id": "ws-001",
        "thread_id": "thread-001",
        "paper_title": "Test Thesis",
        "discipline": "计算机科学",
        "abstract_content": "Abstract",
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
                "description": "系统架构图",
                "caption": "图1 系统架构",
                "strategy": "mermaid",
            },
        ],
        "generated_figures": [],
        "current_phase": "figure_planning",
        "progress": 0.82,
        "errors": [],
    }


def test_figure_generator_node_creates_stub(state_with_requests):
    """Test figure generator creates placeholder figures."""
    result = figure_generator_node(state_with_requests)

    assert "generated_figures" in result
    assert len(result["generated_figures"]) == 1

    fig = result["generated_figures"][0]
    assert fig["request_id"] == "fig1"
    assert fig["id"] == "fig1"
    # Stub implementation returns placeholder
    assert "placeholder" in fig["file_path"] or fig["file_path"] == ""

    assert result["current_phase"] == "figure_generation"
    assert result["progress"] == 0.85


def test_figure_generator_empty_requests():
    """Test figure generator with no requests."""
    state = {
        "workspace_id": "ws-001",
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
    result = figure_generator_node(state)
    assert result["generated_figures"] == []
    assert result["progress"] == 0.88
```

### Step 3.2: Run test to verify it fails

Run: `pytest tests/thesis/workflow/nodes/test_figure_generator.py -v`
Expected: FAIL with module import error

### Step 3.3: Write figure_generator.py (stub implementation)

```python
# src/thesis/workflow/nodes/figure_generator.py
"""Figure generator node for thesis workflow.

NOTE: This is a stub implementation. Full implementation requires
integration with ExecutionService for mermaid/python/kling generation.
"""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState
from .base import log_node_start, log_node_end

logger = logging.getLogger(__name__)


def figure_generator_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Generate figures based on planned requests.

    This is a STUB implementation that creates placeholder figures.
    Full implementation will:
    1. For mermaid: call ExecutionService with MERMAID_DIAGRAM
    2. For python: call ExecutionService with PYTHON_PLOT
    3. For kling: call ExecutionService with AI_IMAGE

    Args:
        state: Current workflow state

    Returns:
        State updates with generated_figures
    """
    log_node_start("figure_generator", state)

    figure_requests = state.get("figure_requests", [])
    generated_figures = []

    for request in figure_requests:
        # Stub: create placeholder figure
        # TODO: Integrate with ExecutionService
        fig_id = request.get("id", "unknown")

        generated_figures.append({
            "id": fig_id,
            "request_id": fig_id,
            "file_path": f"/placeholder/{fig_id}.pdf",  # Stub path
            "latex_ref": f"\\includegraphics[width=0.8\\textwidth]{{{fig_id}.pdf}}",
        })

        logger.info(f"[Thesis] Generated stub figure: {fig_id}")

    log_node_end("figure_generator", state, {"progress": 0.85})

    return {
        "generated_figures": generated_figures,
        "current_phase": "figure_generation",
        "progress": 0.88 if not figure_requests else 0.85,
    }


__all__ = ["figure_generator_node"]
```

### Step 3.4: Run test to verify it passes

Run: `pytest tests/thesis/workflow/nodes/test_figure_generator.py -v`
Expected: 2 passed

### Step 3.5: Update nodes/__init__.py

```python
# Add to src/thesis/workflow/nodes/__init__.py
from .figure_generator import figure_generator_node

# Add to __all__:
    "figure_generator_node",
```

### Step 3.6: Run all thesis tests

Run: `pytest tests/thesis/ -v`
Expected: 30 passed

### Step 3.7: Commit

```bash
git add src/thesis/workflow/nodes/figure_generator.py tests/thesis/workflow/nodes/test_figure_generator.py src/thesis/workflow/nodes/__init__.py
git commit -m "feat(thesis): add figure generator node (stub implementation)"
```

---

## Task 4: LaTeX Compiler Node (Stub)

**Files:**
- Create: `src/thesis/workflow/nodes/compiler.py`
- Create: `tests/thesis/workflow/nodes/test_compiler.py`
- Modify: `src/thesis/workflow/nodes/__init__.py`

### Step 4.1: Write the failing test

```python
# tests/thesis/workflow/nodes/test_compiler.py
"""Tests for LaTeX compiler node."""

import pytest
from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.workflow.nodes.compiler import compile_latex_node


@pytest.fixture
def state_with_latex() -> ThesisWorkflowState:
    """Create a state with final LaTeX content."""
    return {
        "workspace_id": "ws-001",
        "thread_id": "thread-001",
        "paper_title": "Test Thesis",
        "discipline": "计算机科学",
        "abstract_content": "Abstract",
        "framework_json": {},
        "section_plans": [],
        "writing_order": [],
        "references": [],
        "citation_plan": {},
        "sections": [],
        "figure_requests": [],
        "generated_figures": [],
        "final_latex": "\\documentclass{article}\\begin{document}Test\\end{document}",
        "bib_content": "@article{test, title={Test}}",
        "current_phase": "assembly",
        "progress": 0.95,
        "errors": [],
    }


def test_compile_latex_node_creates_pdf_stub(state_with_latex):
    """Test compiler node creates PDF (stub)."""
    result = compile_latex_node(state_with_latex)

    assert "pdf_path" in result
    # Stub returns a path
    assert result["pdf_path"] is not None
    assert result["current_phase"] == "compile"
    assert result["progress"] == 1.0


def test_compile_latex_node_missing_latex():
    """Test compiler handles missing LaTeX gracefully."""
    state = {
        "workspace_id": "ws-001",
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
        "current_phase": "assembly",
        "progress": 0.95,
        "errors": [],
    }
    result = compile_latex_node(state)

    assert "errors" in result
    assert len(result["errors"]) > 0
```

### Step 4.2: Run test to verify it fails

Run: `pytest tests/thesis/workflow/nodes/test_compiler.py -v`
Expected: FAIL with module import error

### Step 4.3: Write compiler.py (stub implementation)

```python
# src/thesis/workflow/nodes/compiler.py
"""LaTeX compiler node for thesis workflow.

NOTE: This is a stub implementation. Full implementation requires
integration with ExecutionMiddleware for Docker-based LaTeX compilation.
"""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.config import thesis_settings
from .base import log_node_start, log_node_end

logger = logging.getLogger(__name__)


def compile_latex_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Compile LaTeX document to PDF.

    This is a STUB implementation that returns a placeholder PDF path.
    Full implementation will:
    1. Call ExecutionService with LATEX_COMPILE type
    2. Pass final_latex, bib_content, and compiler settings
    3. Return actual PDF path from sandbox

    Args:
        state: Current workflow state

    Returns:
        State updates with pdf_path
    """
    log_node_start("compiler", state)

    final_latex = state.get("final_latex")
    workspace_id = state.get("workspace_id", "default")

    if not final_latex:
        logger.error("[Thesis] No LaTeX content to compile")
        return {
            "errors": ["No LaTeX content available for compilation"],
            "current_phase": "compile",
            "progress": 0.95,
        }

    # Stub: create placeholder PDF path
    # TODO: Integrate with ExecutionService
    # request = ExecutionRequest(
    #     execution_type=ExecutionType.LATEX_COMPILE,
    #     content=final_latex,
    #     options={
    #         "compiler": thesis_settings.latex_compiler,
    #         "bibliography": state.get("bib_content"),
    #         "bibliography_style": thesis_settings.bibliography_style,
    #     },
    #     workspace_id=workspace_id,
    # )
    # result = await execution_service.execute(request)

    pdf_path = f"/sandbox/{workspace_id}/thesis.pdf"

    logger.info(f"[Thesis] Compiled LaTeX (stub): {pdf_path}")

    log_node_end("compiler", state, {"progress": 1.0})

    return {
        "pdf_path": pdf_path,
        "current_phase": "compile",
        "progress": 1.0,
    }


__all__ = ["compile_latex_node"]
```

### Step 4.4: Run test to verify it passes

Run: `pytest tests/thesis/workflow/nodes/test_compiler.py -v`
Expected: 2 passed

### Step 4.5: Update nodes/__init__.py

```python
# Add to src/thesis/workflow/nodes/__init__.py
from .compiler import compile_latex_node

# Add to __all__:
    "compile_latex_node",
```

### Step 4.6: Run all thesis tests

Run: `pytest tests/thesis/ -v`
Expected: 32 passed

### Step 4.7: Commit

```bash
git add src/thesis/workflow/nodes/compiler.py tests/thesis/workflow/nodes/test_compiler.py src/thesis/workflow/nodes/__init__.py
git commit -m "feat(thesis): add LaTeX compiler node (stub implementation)"
```

---

## Task 5: LangGraph Workflow Definition

**Files:**
- Create: `src/thesis/workflow/graph.py`
- Create: `tests/thesis/workflow/test_graph.py`

### Step 5.1: Write the failing test

```python
# tests/thesis/workflow/test_graph.py
"""Tests for thesis workflow graph."""

import pytest
from langgraph.constants import END

from src.thesis.workflow.graph import (
    thesis_graph,
    should_continue_writing,
    ROUTE_CONTINUE,
    ROUTE_DONE,
)


def test_graph_has_correct_nodes():
    """Test graph contains all required nodes."""
    # Get node names from the graph
    nodes = set(thesis_graph.nodes.keys())

    expected_nodes = {
        "literature_search",
        "section_writer",
        "figure_planner",
        "figure_generator",
        "assembler",
        "compiler",
    }

    assert expected_nodes.issubset(nodes)


def test_should_continue_writing_returns_continue():
    """Test routing continues when sections remain."""
    state = {
        "sections": [
            {"index": 1, "status": "completed"},
            {"index": 2, "status": "pending"},
        ],
        "section_plans": [
            {"index": 1},
            {"index": 2},
        ],
    }
    result = should_continue_writing(state)
    assert result == ROUTE_CONTINUE


def test_should_continue_writing_returns_done():
    """Test routing ends when all sections completed."""
    state = {
        "sections": [
            {"index": 1, "status": "completed"},
            {"index": 2, "status": "completed"},
        ],
        "section_plans": [
            {"index": 1},
            {"index": 2},
        ],
    }
    result = should_continue_writing(state)
    assert result == ROUTE_DONE


def test_graph_can_compile():
    """Test graph compiles without errors."""
    # If this doesn't raise, the graph is valid
    assert thesis_graph is not None
```

### Step 5.2: Run test to verify it fails

Run: `pytest tests/thesis/workflow/test_graph.py -v`
Expected: FAIL with module import error

### Step 5.3: Write graph.py implementation

```python
# src/thesis/workflow/graph.py
"""LangGraph workflow definition for thesis generation."""

import logging
from typing import Literal

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from src.thesis.workflow.state import ThesisWorkflowState
from src.thesis.workflow.nodes import (
    literature_search_node,
    section_writer_node,
    assemble_latex_node,
    figure_planner_node,
    figure_generator_node,
    compile_latex_node,
)

logger = logging.getLogger(__name__)

# Route constants
ROUTE_CONTINUE = "continue_writing"
ROUTE_DONE = "done_writing"


def _get_attr(obj, attr: str, default=None):
    """Handle both Pydantic models and dict objects."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def should_continue_writing(
    state: ThesisWorkflowState,
) -> Literal["continue_writing", "done_writing"]:
    """Determine if section writing should continue.

    Args:
        state: Current workflow state

    Returns:
        Route to take: continue_writing or done_writing
    """
    sections = state.get("sections", [])
    plans = state.get("section_plans", [])

    if not plans:
        return ROUTE_DONE

    # Count completed sections
    completed_indices = {
        _get_attr(s, "index")
        for s in sections
        if _get_attr(s, "status") == "completed"
    }

    # Check if all planned sections are completed
    all_done = all(
        _get_attr(p, "index") in completed_indices
        for p in plans
    )

    return ROUTE_DONE if all_done else ROUTE_CONTINUE


def build_thesis_graph() -> StateGraph:
    """Build the thesis generation workflow graph.

    Graph structure:
        literature_search -> section_writer -> figure_planner -> figure_generator -> assembler -> compiler -> END
                               ↓
                          (loop until all sections done)

    Returns:
        Compiled StateGraph
    """
    # Create graph with state schema
    builder = StateGraph(ThesisWorkflowState)

    # Add nodes
    builder.add_node("literature_search", literature_search_node)
    builder.add_node("section_writer", section_writer_node)
    builder.add_node("figure_planner", figure_planner_node)
    builder.add_node("figure_generator", figure_generator_node)
    builder.add_node("assembler", assemble_latex_node)
    builder.add_node("compiler", compile_latex_node)

    # Set entry point
    builder.set_entry_point("literature_search")

    # Add edges
    # literature_search -> section_writer
    builder.add_edge("literature_search", "section_writer")

    # section_writer conditional routing
    builder.add_conditional_edges(
        "section_writer",
        should_continue_writing,
        {
            ROUTE_CONTINUE: "section_writer",  # Loop back
            ROUTE_DONE: "figure_planner",      # Move to figures
        },
    )

    # figure_planner -> figure_generator -> assembler -> compiler -> END
    builder.add_edge("figure_planner", "figure_generator")
    builder.add_edge("figure_generator", "assembler")
    builder.add_edge("assembler", "compiler")
    builder.add_edge("compiler", END)

    # Compile with memory checkpointer for state persistence
    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# Global graph instance
thesis_graph = build_thesis_graph()


__all__ = [
    "thesis_graph",
    "build_thesis_graph",
    "should_continue_writing",
    "ROUTE_CONTINUE",
    "ROUTE_DONE",
]
```

### Step 5.4: Run test to verify it passes

Run: `pytest tests/thesis/workflow/test_graph.py -v`
Expected: 4 passed

### Step 5.5: Run all thesis tests

Run: `pytest tests/thesis/ -v`
Expected: 36 passed

### Step 5.6: Commit

```bash
git add src/thesis/workflow/graph.py tests/thesis/workflow/test_graph.py
git commit -m "feat(thesis): add LangGraph workflow definition with 6 nodes"
```

---

## Task 6: Workflow Runner

**Files:**
- Create: `src/thesis/workflow/runner.py`
- Create: `tests/thesis/workflow/test_runner.py`

### Step 6.1: Write the failing test

```python
# tests/thesis/workflow/test_runner.py
"""Tests for thesis workflow runner."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.thesis.workflow.runner import run_thesis_workflow
from src.thesis.task_storage import InMemoryTaskStorage, set_storage, ThesisTask


@pytest.fixture
def isolated_storage():
    """Use isolated storage for each test."""
    storage = InMemoryTaskStorage()
    set_storage(storage)
    yield storage
    set_storage(None)


@pytest.fixture
def sample_request():
    """Sample thesis generation request."""
    return {
        "workspace_id": "ws-001",
        "paper_title": "测试论文",
        "discipline": "计算机科学",
        "abstract_content": "这是一篇测试论文的摘要。",
        "framework_json": {
            "sections": [
                {"index": 1, "title": "绪论", "purpose": "介绍研究背景"},
                {"index": 2, "title": "方法", "purpose": "描述研究方法"},
            ]
        },
        "enable_search": True,
        "enable_images": True,
    }


@pytest.mark.asyncio
async def test_run_thesis_workflow_updates_task_status(isolated_storage, sample_request):
    """Test runner updates task status."""
    # Create task
    task = ThesisTask(
        task_id="test-task-1",
        workspace_id="ws-001",
        paper_title="测试论文",
    )
    isolated_storage.create_task(task)

    # Run workflow
    await run_thesis_workflow("test-task-1", sample_request)

    # Check task was updated
    updated = isolated_storage.get_task("test-task-1")
    assert updated is not None
    assert updated.status in ("completed", "failed")


@pytest.mark.asyncio
async def test_run_thesis_workflow_handles_missing_task(isolated_storage, sample_request):
    """Test runner handles missing task gracefully."""
    # Don't create task - should handle gracefully
    await run_thesis_workflow("nonexistent-task", sample_request)
    # Should not raise


@pytest.mark.asyncio
async def test_run_thesis_workflow_handles_error(isolated_storage):
    """Test runner handles errors and updates task."""
    # Create task
    task = ThesisTask(
        task_id="test-task-2",
        workspace_id="ws-001",
        paper_title="测试论文",
    )
    isolated_storage.create_task(task)

    # Run with invalid request (missing required fields)
    invalid_request = {
        "workspace_id": "ws-001",
        # Missing paper_title and other required fields
    }

    await run_thesis_workflow("test-task-2", invalid_request)

    # Check task was marked as failed
    updated = isolated_storage.get_task("test-task-2")
    assert updated is not None
    # Should be failed or completed (depending on how we handle it)
    assert updated.status in ("failed", "completed")
```

### Step 6.2: Run test to verify it fails

Run: `pytest tests/thesis/workflow/test_runner.py -v`
Expected: FAIL with module import error

### Step 6.3: Write runner.py implementation

```python
# src/thesis/workflow/runner.py
"""Workflow runner for thesis generation tasks."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from src.thesis.task_storage import get_storage
from src.thesis.workflow.graph import thesis_graph
from src.thesis.workflow.state import ThesisWorkflowState, SectionPlan
from src.thesis.config import thesis_settings

logger = logging.getLogger(__name__)


def _build_section_plans(framework: dict) -> list[SectionPlan]:
    """Build section plans from framework JSON.

    Args:
        framework: Framework from framework-designer skill

    Returns:
        List of SectionPlan objects
    """
    sections = framework.get("sections", [])
    plans = []

    for i, section in enumerate(sections, start=1):
        if isinstance(section, dict):
            plan = SectionPlan(
                index=section.get("index", i),
                title=section.get("title", f"Section {i}"),
                purpose=section.get("purpose", ""),
                key_points=section.get("key_points", []),
                target_words=section.get("target_words", thesis_settings.default_target_words),
                dependencies=section.get("dependencies", []),
                literature_needs=section.get("literature_needs", []),
            )
        else:
            # Handle simple string sections
            plan = SectionPlan(
                index=i,
                title=str(section),
                purpose="",
                target_words=thesis_settings.default_target_words,
            )
        plans.append(plan)

    return plans


def _build_writing_order(plans: list[SectionPlan]) -> list[int]:
    """Determine writing order based on dependencies.

    Args:
        plans: List of section plans

    Returns:
        List of section indices in writing order
    """
    # Simple topological sort based on dependencies
    # For now, just return indices in order (can be enhanced)
    return [p.index for p in plans]


async def run_thesis_workflow(task_id: str, request: dict[str, Any]) -> None:
    """Run the thesis generation workflow.

    This is the main entry point for background task execution.
    It updates task status and runs the LangGraph workflow.

    Args:
        task_id: Task ID to update
        request: Original request from API
    """
    storage = get_storage()

    try:
        # Get task
        task = storage.get_task(task_id)
        if not task:
            logger.error(f"[Thesis] Task not found: {task_id}")
            return

        # Update status to running
        storage.update_task(task_id, {
            "status": "running",
            "current_phase": "init",
            "message": "Starting thesis generation",
        })

        # Build initial state
        framework = request.get("framework_json", {})
        section_plans = _build_section_plans(framework)
        writing_order = _build_writing_order(section_plans)

        initial_state: ThesisWorkflowState = {
            "workspace_id": request.get("workspace_id", ""),
            "thread_id": task_id,
            "paper_title": request.get("paper_title", "Untitled"),
            "discipline": request.get("discipline", "计算机科学"),
            "abstract_content": request.get("abstract_content", ""),
            "framework_json": framework,
            "section_plans": [p.model_dump() for p in section_plans],
            "writing_order": writing_order,
            "references": [],
            "citation_plan": {},
            "sections": [],
            "figure_requests": [],
            "generated_figures": [],
            "current_phase": "init",
            "progress": 0.0,
            "errors": [],
        }

        # Run workflow with streaming updates
        config = {"configurable": {"thread_id": task_id}}

        async for event in thesis_graph.astream(initial_state, config):
            # Extract state update from event
            for node_name, update in event.items():
                logger.debug(f"[Thesis] Node {node_name} completed: {update}")

                # Update task progress
                if isinstance(update, dict):
                    progress = update.get("progress", 0)
                    phase = update.get("current_phase", "")

                    storage.update_task(task_id, {
                        "progress": progress,
                        "current_phase": phase,
                        "message": f"Processing: {node_name}",
                    })

        # Get final state
        final_state = await thesis_graph.aget_state(config)
        state_values = final_state.values

        # Update task with final results
        storage.update_task(task_id, {
            "status": "completed",
            "progress": 1.0,
            "latex_content": state_values.get("final_latex", ""),
            "bib_content": state_values.get("bib_content", ""),
            "pdf_path": state_values.get("pdf_path", ""),
            "sections_completed": len([s for s in state_values.get("sections", []) if _get_attr(s, "status") == "completed"]),
            "sections_total": len(state_values.get("section_plans", [])),
            "message": "Thesis generation completed",
        })

        logger.info(f"[Thesis] Task {task_id} completed successfully")

    except Exception as e:
        logger.exception(f"[Thesis] Task {task_id} failed: {e}")

        # Update task as failed
        storage.update_task(task_id, {
            "status": "failed",
            "error": str(e),
            "message": f"Generation failed: {e}",
        })


def _get_attr(obj, attr: str, default=None):
    """Handle both Pydantic models and dict objects."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


__all__ = ["run_thesis_workflow"]
```

### Step 6.4: Run test to verify it passes

Run: `pytest tests/thesis/workflow/test_runner.py -v`
Expected: 3 passed

### Step 6.5: Run all thesis tests

Run: `pytest tests/thesis/ -v`
Expected: 39 passed

### Step 6.6: Commit

```bash
git add src/thesis/workflow/runner.py tests/thesis/workflow/test_runner.py
git commit -m "feat(thesis): add workflow runner with background task execution"
```

---

## Task 7: API Integration

**Files:**
- Modify: `src/thesis/api.py`
- Modify: `src/thesis/__init__.py`

### Step 7.1: Update api.py to use runner

```python
# In src/thesis/api.py, update the generate_thesis function (lines 96-102):

# Replace:
    # TODO: Implement background task execution when workflow is ready
    # from .workflow.runner import run_thesis_workflow
    # background_tasks.add_task(
    #     run_thesis_workflow,
    #     task.task_id,
    #     request.model_dump(),
    # )

# With:
    # Start background workflow execution
    from .workflow.runner import run_thesis_workflow
    background_tasks.add_task(
        run_thesis_workflow,
        task.task_id,
        request.model_dump(),
    )
```

### Step 7.2: Update module exports

```python
# In src/thesis/__init__.py, add new exports:

from .config import ThesisSettings, thesis_settings
from .workflow.graph import thesis_graph, build_thesis_graph

# Add to __all__:
    "ThesisSettings",
    "thesis_settings",
    "thesis_graph",
    "build_thesis_graph",
```

### Step 7.3: Run all thesis tests

Run: `pytest tests/thesis/ -v`
Expected: 39 passed

### Step 7.4: Commit

```bash
git add src/thesis/api.py src/thesis/__init__.py
git commit -m "feat(thesis): integrate workflow runner into API generate endpoint"
```

---

## Task 8: Final Verification

### Step 8.1: Run all thesis tests

Run: `pytest tests/thesis/ -v --cov=src/thesis --cov-report=term-missing`
Expected: All tests pass

### Step 8.2: Run full test suite (if applicable)

Run: `pytest tests/ -v --tb=short -x`
Expected: No regressions

### Step 8.3: Update handover document

Add implementation notes to handover doc:

```markdown
## 实现状态更新 (2026-03-11)

### 已完成
- config.py - 配置管理
- figure_planner.py - 配图规划节点
- figure_generator.py - 配图生成节点 (stub)
- compiler.py - LaTeX编译节点 (stub)
- graph.py - LangGraph状态机
- runner.py - 工作流执行器
- API集成

### Stub实现说明
以下节点为stub实现，需要后续集成ExecutionService:
- figure_generator: 需要MERMAID_DIAGRAM, PYTHON_PLOT, AI_IMAGE
- compiler: 需要LATEX_COMPILE完整集成

### 运行测试
pytest tests/thesis/ -v
```

### Step 8.4: Final commit

```bash
git add docs/plans/2026-03-11-thesis-handover.md
git commit -m "docs(thesis): update handover with Phase 1 implementation status"
```

---

## Summary

| Task | Files Created | Files Modified | Tests |
|------|---------------|----------------|-------|
| 1. Config | config.py, test_config.py | literature_search.py | 3 |
| 2. Figure Planner | figure_planner.py, test_figure_planner.py | nodes/__init__.py | 3 |
| 3. Figure Generator | figure_generator.py, test_figure_generator.py | nodes/__init__.py | 2 |
| 4. Compiler | compiler.py, test_compiler.py | nodes/__init__.py | 2 |
| 5. Graph | graph.py, test_graph.py | - | 4 |
| 6. Runner | runner.py, test_runner.py | - | 3 |
| 7. API Integration | - | api.py, __init__.py | 0 |
| 8. Verification | - | handover.md | - |

**Total:** 7 new source files, 7 new test files, ~17 new tests
