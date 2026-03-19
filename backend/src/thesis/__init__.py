"""Thesis module for undergraduate thesis generation.

This module provides:
- Workflow state definitions for thesis generation
- Workflow nodes for each generation phase
- API endpoints for thesis generation requests
- Subagent configurations for thesis-specific tasks

Integration points:
- MemoryMiddleware: Automatically captures thesis discussion context
- ExecutionMiddleware: Handles LaTeX compilation via compile_latex_tool
- SubagentRegistry: Provides thesis_writer, librarian, figure_planner
"""

from .config import (
    ThesisSettings,
    thesis_settings,
)
from .workflow.graph import (
    build_thesis_graph,
    thesis_graph,
)
from .workflow.nodes import (
    assemble_latex_node,
    check_literature_sufficiency,
    generate_bibtex,
    get_next_section_index,
    literature_search_node,
    section_writer_node,
)
from .workflow.state import (
    SectionContent,
    SectionPlan,
    ThesisWorkflowState,
    merge_errors,
    merge_references,
    merge_sections,
)

__all__ = [
    # State types
    "SectionPlan",
    "SectionContent",
    "ThesisWorkflowState",
    # Reducers
    "merge_sections",
    "merge_references",
    "merge_errors",
    # Workflow nodes
    "section_writer_node",
    "get_next_section_index",
    "literature_search_node",
    "check_literature_sufficiency",
    "assemble_latex_node",
    "generate_bibtex",
    # Configuration
    "ThesisSettings",
    "thesis_settings",
    # Workflow graph
    "thesis_graph",
    "build_thesis_graph",
]
