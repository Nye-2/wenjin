# src/thesis/workflow/nodes/figure_planner.py
"""Figure planner node for thesis workflow.

This node scans completed sections for figure placeholders
and plans the generation strategy for each figure.
"""

import logging
import re
from typing import Any

from src.thesis.workflow.state import ThesisWorkflowState

from .base import get_attr, log_node_end, log_node_start

logger = logging.getLogger(__name__)

# Pattern to match figure placeholders in section content
# Format: % [FIGURE:id|type|description|caption]
PLACEHOLDER_PATTERN = re.compile(
    r"%\s*\[FIGURE:([^|]+)\|([^|]+)\|([^|]+)\|([^\]]+)\]"
)


def extract_figure_placeholders(content: str) -> list[dict]:
    """Extract figure placeholders from section content.

    Args:
        content: Section content text containing figure placeholders

    Returns:
        List of dicts with keys: id, figure_type, description, caption
    """
    matches = PLACEHOLDER_PATTERN.findall(content)
    result = []
    for match in matches:
        result.append({
            "id": match[0].strip(),
            "figure_type": match[1].strip().lower(),
            "description": match[2].strip(),
            "caption": match[3].strip(),
        })
    return result


def determine_strategy(figure_type: str) -> str:
    """Determine the generation strategy based on figure type.

    Args:
        figure_type: Type of figure (architecture, flowchart, chart, etc.)

    Returns:
        Strategy name: "mermaid", "python", or "kling"
    """
    figure_type = figure_type.lower().strip()

    # Architecture, flowchart, and diagram types use Mermaid
    if figure_type in ("architecture", "flowchart", "diagram"):
        return "mermaid"

    # Chart and graph types use Python (matplotlib/plotly)
    if figure_type in ("chart", "graph"):
        return "python"

    # Concept illustrations use Kling AI
    if figure_type == "concept":
        return "kling"

    # Default to mermaid for unknown types
    return "mermaid"


def figure_planner_node(state: ThesisWorkflowState) -> dict[str, Any]:
    """Scan completed sections for figure placeholders and plan generation.

    This node:
    1. Iterates through all sections
    2. Scans completed sections for figure placeholders
    3. Determines generation strategy for each figure
    4. Returns figure requests for the figure generator node

    Args:
        state: Current workflow state

    Returns:
        State updates with figure_requests list
    """
    log_node_start("figure_planner", state)

    sections = state.get("sections", [])
    figure_requests = []

    for section in sections:
        # Only process completed sections
        status = get_attr(section, "status", "pending")
        if status != "completed":
            continue

        section_index = get_attr(section, "index")
        content = get_attr(section, "content", "")

        # Extract placeholders from section content
        placeholders = extract_figure_placeholders(content)

        for placeholder in placeholders:
            strategy = determine_strategy(placeholder["figure_type"])
            figure_requests.append({
                "id": placeholder["id"],
                "section_index": section_index,
                "figure_type": placeholder["figure_type"],
                "description": placeholder["description"],
                "caption": placeholder["caption"],
                "strategy": strategy,
            })

    logger.info(
        f"[Thesis:{state.get('workspace_id', 'unknown')}] "
        f"Found {len(figure_requests)} figure requests"
    )

    log_node_end("figure_planner", state, {"figure_count": len(figure_requests)})

    return {
        "figure_requests": figure_requests,
        "current_phase": "figure_planning",
        "progress": 0.82,
    }
