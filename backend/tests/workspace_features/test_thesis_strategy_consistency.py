"""thesis_feature_service is the single source for figure strategy mapping."""

from src.agents.graphs.thesis.figure_generation import (
    _FIGURE_STRATEGY_BY_TYPE as GRAPH_MAPPING,
)
from src.workspace_features.services.thesis_feature_service import (
    _FIGURE_STRATEGY_BY_TYPE as SERVICE_MAPPING,
)


def test_figure_strategy_mappings_are_identical():
    """Both references must point to the same canonical dict — no drift."""
    assert SERVICE_MAPPING is GRAPH_MAPPING, (
        "figure_generation.py must import _FIGURE_STRATEGY_BY_TYPE from "
        "thesis_feature_service.py, not define its own copy. "
        f"Diff: {set(SERVICE_MAPPING.items()) ^ set(GRAPH_MAPPING.items())}"
    )
