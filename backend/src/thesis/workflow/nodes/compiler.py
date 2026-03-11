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
