# src/thesis/workflow/nodes/__init__.py
"""Thesis workflow nodes."""

from .assembler import assemble_latex_node, generate_bibtex
from .compiler import compile_latex_node
from .figure_generator import figure_generator_node
from .figure_planner import (
    PLACEHOLDER_PATTERN,
    determine_strategy,
    extract_figure_placeholders,
    figure_planner_node,
)
from .literature_search import check_literature_sufficiency, literature_search_node
from .section_writer import get_next_section_index, section_writer_node

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
