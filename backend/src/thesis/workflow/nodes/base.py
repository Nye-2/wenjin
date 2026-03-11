# src/thesis/workflow/nodes/base.py
"""Base utilities for workflow nodes."""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState

logger = logging.getLogger(__name__)


def get_attr(obj: Any, attr: str, default: Any = None) -> Any:
    """Get attribute from dict or Pydantic model.

    Handles both dict and Pydantic model objects uniformly.
    Used throughout thesis nodes for type-safe attribute access.

    Args:
        obj: Object to get attribute from (dict or Pydantic model)
        attr: Attribute name to retrieve
        default: Default value if attribute not found

    Returns:
        Attribute value or default
    """
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def calculate_progress(state: ThesisWorkflowState, phase: str | None) -> float:
    """Calculate current progress based on state.

    Progress allocation:
    - 0.00-0.15: initialization, literature search
    - 0.15-0.80: section writing (proportional to completed sections)
    - 0.80-0.90: figure generation
    - 0.90-0.95: assembly
    - 0.95-1.00: LaTeX compilation
    """
    phase_progress = {
        "init": 0.05,
        "literature_search": 0.15,
        "writing": 0.80,
        "figures": 0.90,
        "assembly": 0.95,
        "compile": 1.00,
    }

    if phase and phase in phase_progress:
        return phase_progress[phase]

    # Calculate based on sections
    plans = state.get("section_plans", [])
    sections = state.get("sections", [])
    if not plans:
        return 0.0

    completed = sum(1 for s in sections if get_attr(s, "status", "pending") == "completed")
    writing_range = 0.65  # 0.80 - 0.15
    return 0.15 + (completed / len(plans)) * writing_range


def log_node_start(node_name: str, state: ThesisWorkflowState):
    """Log node execution start."""
    logger.info(f"[Thesis:{state['workspace_id']}] {node_name} started")


def log_node_end(node_name: str, state: ThesisWorkflowState, updates: dict[str, Any]):
    """Log node execution end."""
    progress = updates.get("progress", state.get("progress", 0))
    logger.info(f"[Thesis:{state['workspace_id']}] {node_name} completed, progress={progress:.1%}")
