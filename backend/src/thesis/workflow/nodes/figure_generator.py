# src/thesis/workflow/nodes/figure_generator.py
"""Figure generator node for thesis workflow.

This node generates figures based on figure_requests using ExecutionService.
Supports three strategies: mermaid (diagrams), python (plots), kling (AI images).
"""

import logging
from typing import Any

from src.thesis.execution.figure_tool import generate_figure
from src.thesis.workflow.state import ThesisWorkflowState

from .base import get_attr, log_node_end, log_node_start

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
                "caption": caption,
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
                "caption": caption,
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
