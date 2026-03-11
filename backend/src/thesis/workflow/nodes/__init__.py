# src/thesis/workflow/nodes/__init__.py
"""Thesis workflow nodes."""

from .section_writer import section_writer_node, get_next_section_index
from .literature_search import literature_search_node, check_literature_sufficiency
from .assembler import assemble_latex_node, generate_bibtex
from .figure_planner import (
    figure_planner_node,
    extract_figure_placeholders,
    determine_strategy,
    PLACEHOLDER_PATTERN,
)
from .figure_generator import figure_generator_node
from .compiler import compile_latex_node

__all__ = [
    "section_writer_node",
    "get_next_section_index",
    "literature_search_node",
    "check_literature_sufficiency",
    "assemble_latex_node",
    "generate_bibtex",
    "figure_planner_node",
    "extract_figure_placeholders",
    "determine_strategy",
    "PLACEHOLDER_PATTERN",
    "figure_generator_node",
    "compile_latex_node",
]
