"""Thesis workflow module."""

from .state import (
    SectionPlan,
    SectionContent,
    SectionStatus,
    PaperReference,
    FigureRequest,
    GeneratedFigure,
    ThesisWorkflowState,
    merge_sections,
    merge_references,
    merge_errors,
)
from .latex_template import (
    THESIS_TEMPLATE_ZH,
    THESIS_TEMPLATE_EN,
    THESIS_TEMPLATE,
    get_template,
)
from .graph import (
    ROUTE_CONTINUE,
    ROUTE_DONE,
    should_continue_writing,
    build_thesis_graph,
    thesis_graph,
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
