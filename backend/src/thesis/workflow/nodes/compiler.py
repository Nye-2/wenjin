# src/thesis/workflow/nodes/compiler.py
"""LaTeX compiler node for thesis workflow.

This node compiles the final LaTeX document to PDF.
Currently a STUB implementation that returns placeholder PDF path.

TODO: Integrate with ExecutionService
Future implementation will:
1. Call ExecutionService with ExecutionType.LATEX_COMPILE
2. Pass compiler options from thesis_settings
3. Handle compilation errors and retry logic
4. Return actual PDF path from sandbox

Example integration:
    from src.execution import ExecutionService, ExecutionRequest, ExecutionType
    from src.thesis.config import thesis_settings

    request = ExecutionRequest(
        execution_type=ExecutionType.LATEX_COMPILE,
        content=final_latex,
        options={
            "compiler": thesis_settings.latex_compiler,
            "bibliography": state.get("bib_content"),
            "bibliography_style": thesis_settings.bibliography_style,
        },
        workspace_id=workspace_id,
    )
    result = await execution_service.execute(request)
"""

import logging
from typing import Any

from src.thesis.config import thesis_settings
from src.thesis.workflow.state import ThesisWorkflowState
from .base import log_node_start, log_node_end

logger = logging.getLogger(__name__)


def compile_latex_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Compile LaTeX document to PDF.

    This is a STUB implementation that returns a placeholder PDF path.
    Future implementation will integrate with ExecutionService for actual
    LaTeX compilation.

    Args:
        state: Current workflow state containing final_latex

    Returns:
        State updates with pdf_path on success, or error message on failure
    """
    log_node_start("compiler", state)

    workspace_id = state.get("workspace_id", "unknown")
    final_latex = state.get("final_latex")

    # Check if final_latex exists
    if not final_latex:
        error_msg = "Cannot compile: final_latex not found in state"
        logger.error(f"[Thesis:{workspace_id}] {error_msg}")

        return {
            "errors": [error_msg],
            "current_phase": "compile",
            "progress": 0.95,  # Stay at assembly progress
        }

    # Log compiler configuration (for future use with ExecutionService)
    logger.info(
        f"[Thesis:{workspace_id}] Compiling LaTeX with "
        f"compiler={thesis_settings.latex_compiler}, "
        f"bibliography_style={thesis_settings.bibliography_style}"
    )

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

    # Stub: return placeholder PDF path
    pdf_path = f"/sandbox/{workspace_id}/thesis.pdf"

    logger.info(f"[Thesis:{workspace_id}] Generated stub PDF path: {pdf_path}")

    log_node_end("compiler", state, {"pdf_path": pdf_path})

    return {
        "pdf_path": pdf_path,
        "current_phase": "compile",
        "progress": 1.0,
    }
