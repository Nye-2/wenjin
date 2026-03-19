"""Tests for thesis subagent configurations."""

from src.subagents.academic.registry import (
    get_all_subagent_types,
    get_subagent_config,
)


def test_thesis_writer_in_registry():
    """Test that thesis_writer is registered."""
    config = get_subagent_config("thesis_writer")
    assert config is not None
    assert config.name == "ThesisWriter"
    assert "read_file" in config.tools
    assert "write_file" in config.tools


def test_librarian_in_registry():
    """Test that librarian is registered."""
    config = get_subagent_config("librarian")
    assert config is not None
    assert config.name == "Librarian"
    assert "semantic_scholar_search" in config.tools


def test_figure_planner_in_registry():
    """Test that figure_planner is registered."""
    config = get_subagent_config("figure_planner")
    assert config is not None
    assert config.name == "FigurePlanner"


def test_all_subagent_types_includes_thesis():
    """Test that thesis types are in all types list."""
    types = get_all_subagent_types()
    assert "thesis_writer" in types
    assert "librarian" in types
    assert "figure_planner" in types
