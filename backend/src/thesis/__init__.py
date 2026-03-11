"""Thesis module for undergraduate thesis generation."""

from .workflow.state import (
    SectionPlan,
    SectionContent,
    ThesisWorkflowState,
    merge_sections,
    merge_references,
    merge_errors,
)

__all__ = [
    "SectionPlan",
    "SectionContent",
    "ThesisWorkflowState",
    "merge_sections",
    "merge_references",
    "merge_errors",
]
