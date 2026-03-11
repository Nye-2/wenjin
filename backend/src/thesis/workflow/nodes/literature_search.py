# src/thesis/workflow/nodes/literature_search.py
"""Literature search node for thesis workflow."""

import logging
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState
from .base import log_node_start, log_node_end

logger = logging.getLogger(__name__)

# Minimum references required for undergraduate thesis
MIN_REFERENCES = 10
RECOMMENDED_REFERENCES = 20


def check_literature_sufficiency(state: ThesisWorkflowState) -> tuple[bool, int]:
    """Check if current references are sufficient for thesis writing.

    Args:
        state: Current workflow state

    Returns:
        Tuple of (is_sufficient, current_count)
    """
    references = state.get("references", [])
    count = len(references)
    return count >= MIN_REFERENCES, count


def literature_search_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Search for literature relevant to the thesis topic.

    This node:
    1. Checks if existing references are sufficient
    2. If not, prepares search queries for the librarian subagent
    3. Returns state updates for literature search phase

    The actual search is performed by the librarian subagent via task_tool.

    Args:
        state: Current workflow state

    Returns:
        State updates for literature search phase
    """
    log_node_start("literature_search", state)

    is_sufficient, count = check_literature_sufficiency(state)

    if is_sufficient:
        logger.info(f"[Thesis] Literature sufficient: {count} references")
        return {
            "current_phase": "citation_planning",
            "progress": 0.15,
        }

    logger.info(f"[Thesis] Literature insufficient: {count}/{MIN_REFERENCES} references")

    # Prepare search context (will be used by librarian subagent)
    paper_title = state.get("paper_title", "")
    discipline = state.get("discipline", "通用")
    abstract = state.get("abstract_content", "")

    # Build search queries based on thesis topic
    # The librarian subagent will use these to search
    search_context = {
        "paper_title": paper_title,
        "discipline": discipline,
        "abstract_summary": abstract[:500] if abstract else "",
        "current_ref_count": count,
        "target_ref_count": RECOMMENDED_REFERENCES,
    }

    log_node_end("literature_search", state, {"progress": 0.10})

    return {
        "current_phase": "literature_search",
        "progress": 0.10,
        # Search context is stored for subagent use
        "_search_context": search_context,
    }
