# src/thesis/workflow/nodes/section_writer.py
"""Section writer node for thesis workflow."""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState, SectionContent, SectionPlan
from .base import calculate_progress, log_node_start, log_node_end

logger = logging.getLogger(__name__)


def _get_attr(obj, attr: str, default=None):
    """Handle both Pydantic models and dict objects."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def get_next_section_index(state: ThesisWorkflowState) -> int | None:
    """Get the next section index to write based on writing_order.

    Args:
        state: Current workflow state

    Returns:
        Next section index to write, or None if all completed
    """
    writing_order = state.get("writing_order", [])
    sections = state.get("sections", [])

    # Get completed section indices
    completed_indices = {
        _get_attr(s, "index")
        for s in sections
        if _get_attr(s, "status", "pending") == "completed"
    }

    # Find first uncompleted section in writing_order
    for idx in writing_order:
        if idx not in completed_indices:
            return idx

    return None


def section_writer_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Write a single thesis section using ThesisWriter subagent.

    This node:
    1. Gets the next section to write
    2. Builds the writing prompt with context
    3. Delegates to thesis_writer subagent (via task tool)
    4. Returns the written content

    Note: Actual subagent execution happens via task_tool in the agent loop.
    This function prepares the state update for the workflow.

    Args:
        state: Current workflow state

    Returns:
        State updates with written section content
    """
    log_node_start("section_writer", state)

    next_idx = get_next_section_index(state)
    if next_idx is None:
        # All sections completed
        return {
            "current_phase": "figures",
            "progress": 0.80,
        }

    # Get section plan
    plans = state.get("section_plans", [])
    section_plan = next((p for p in plans if _get_attr(p, "index") == next_idx), None)
    if not section_plan:
        logger.error(f"Section plan not found for index {next_idx}")
        return {"errors": [f"Section plan not found for index {next_idx}"]}

    # Build context for the subagent
    # (This would be passed to the task tool in actual execution)
    _ = state.get("paper_title")
    _ = state.get("discipline")
    _ = state.get("abstract_content")

    # Get citation context for this section
    citation_plan = state.get("citation_plan", {})
    section_refs = citation_plan.get(next_idx, [])

    # Mark section as in-progress
    in_progress_section = SectionContent(
        index=next_idx,
        title=_get_attr(section_plan, "title", f"Section {next_idx}"),
        content="",  # Will be filled by subagent
        status="writing",
    )

    progress = calculate_progress(state, "writing")

    log_node_end("section_writer", state, {"current_section_index": next_idx})

    return {
        "sections": [in_progress_section],
        "current_section_index": next_idx,
        "current_phase": "writing",
        "progress": progress,
    }
