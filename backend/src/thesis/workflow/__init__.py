"""Thesis workflow module."""

from .graph import (
    ROUTE_CONTINUE,
    ROUTE_DONE,
    build_thesis_graph,
    should_continue_writing,
    thesis_graph,
)
from .latex_template import (
    THESIS_TEMPLATE,
    THESIS_TEMPLATE_EN,
    THESIS_TEMPLATE_ZH,
    get_template,
)
from .state import (
    FigureRequest,
    GeneratedFigure,
    PaperReference,
    SectionContent,
    SectionPlan,
    SectionStatus,
    ThesisWorkflowState,
    merge_errors,
    merge_references,
    merge_sections,
)

__all__ = [
    # State types
    "SectionPlan",
    "SectionContent",
    "SectionStatus",
    "PaperReference",
    "FigureRequest",
    "GeneratedFigure",
    "ThesisWorkflowState",
    # Reducers
    "merge_sections",
    "merge_references",
    "merge_errors",
    # Templates
    "THESIS_TEMPLATE_ZH",
    "THESIS_TEMPLATE_EN",
    "THESIS_TEMPLATE",
    "get_template",
    # Graph
    "ROUTE_CONTINUE",
    "ROUTE_DONE",
    "should_continue_writing",
    "build_thesis_graph",
    "thesis_graph",
]
