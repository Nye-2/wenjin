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

from .workflow.state import (
    SectionPlan,
    SectionContent,
    ThesisWorkflowState,
    merge_sections,
    merge_references,
    merge_errors,
)

from .workflow.nodes import (
    section_writer_node,
    get_next_section_index,
    literature_search_node,
    check_literature_sufficiency,
    assemble_latex_node,
    generate_bibtex,
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
]
