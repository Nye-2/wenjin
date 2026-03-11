# src/thesis/workflow/nodes/figure_generator.py
"""Figure generator node for thesis workflow.

This node generates figures based on figure_requests from the state.
Currently a STUB implementation that returns placeholder paths.

TODO: Integrate with ExecutionService
For mermaid: ExecutionType.MERMAID_DIAGRAM
For python: ExecutionType.PYTHON_PLOT
For kling: ExecutionType.AI_IMAGE
"""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState
from .base import log_node_start, log_node_end, get_attr

logger = logging.getLogger(__name__)


def figure_generator_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Generate figures based on figure_requests.

    This is a STUB implementation that returns placeholder paths.
    Future implementation will integrate with ExecutionService for:
    - Mermaid diagram generation
    - Python plot generation
    - AI image generation via Kling

    Args:
        state: Current workflow state

    Returns:
        State updates with generated_figures list
    """
    log_node_start("figure_generator", state)

    figure_requests = state.get("figure_requests", [])
    generated_figures = []

    for request in figure_requests:
        figure_id = get_attr(request, "id")

        # Create stub figure with placeholder path
        generated_figure = {
            "id": figure_id,
            "request_id": figure_id,
            "file_path": f"/placeholder/{figure_id}.pdf",
            "latex_ref": f"\\includegraphics[width=0.8\\textwidth]{{{figure_id}.pdf}}",
        }
        generated_figures.append(generated_figure)

        logger.info(
            f"[Thesis:{state.get('workspace_id', 'unknown')}] "
            f"Generated stub figure: {figure_id}"
        )

    log_node_end(
        "figure_generator",
        state,
        {"generated_count": len(generated_figures)},
    )

    # Progress: 0.85 if there are figures, 0.88 if no figures to generate
    progress = 0.85 if generated_figures else 0.88

    return {
        "generated_figures": generated_figures,
        "current_phase": "figure_generation",
        "progress": progress,
    }
