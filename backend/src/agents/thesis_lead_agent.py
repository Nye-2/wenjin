"""ThesisLeadAgent - Backward compatibility module.

This module now re-exports from workspace_lead_agent.py for unified handling
of all workspace types. Import paths remain unchanged for backward compatibility.

Migration Note:
    All thesis graphs should now import from workspace_lead_agent directly:
    >>> from src.agents.workspace_lead_agent import register_feature_graph
    >>> @register_feature_graph("feature_id", workspace_type="thesis")
    >>> async def my_graph(...): ...

    But legacy imports from this module will continue to work.
"""

# Feature IDs for thesis workspace (for backward compatibility)
THESIS_FEATURE_IDS = (
    "deep_research",
    "literature_management",
    "opening_research",
    "thesis_writing",
    "figure_generation",
    "compile_export",
)

from src.agents.workspace_lead_agent import (
    execute_feature_graph,
    execute_thesis_feature_graph,
    register_feature_graph,
)

__all__ = [
    "THESIS_FEATURE_IDS",
    "execute_feature_graph",
    "execute_thesis_feature_graph",
    "register_feature_graph",
]
