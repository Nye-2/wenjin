# src/thesis/execution/latex_tool.py
"""LaTeX compilation tool for thesis workflow.

Provides async interface to ExecutionService for LaTeX compilation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.execution.types import ExecutionRequest, ExecutionStatus, ExecutionType
from src.thesis.config import thesis_settings

if TYPE_CHECKING:
    from src.thesis.execution import ExecutionServiceProtocol

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
    execution_service: ExecutionServiceProtocol | None = None,
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
                page_count=(result.metadata or {}).get("page_count"),
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
