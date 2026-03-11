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
