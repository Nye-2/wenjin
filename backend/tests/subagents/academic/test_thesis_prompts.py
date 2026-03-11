"""Tests for thesis subagent prompts."""

import pytest
from src.subagents.academic.thesis_prompts import (
    THESIS_WRITER_PROMPT,
    LIBRARIAN_PROMPT,
    FIGURE_PLANNER_PROMPT,
)


def test_thesis_writer_prompt_exists():
    """Test that THESIS_WRITER_PROMPT is defined."""
    assert THESIS_WRITER_PROMPT is not None
    assert len(THESIS_WRITER_PROMPT) > 100
    assert "LaTeX" in THESIS_WRITER_PROMPT
    assert "cite" in THESIS_WRITER_PROMPT.lower()


def test_librarian_prompt_exists():
    """Test that LIBRARIAN_PROMPT is defined."""
    assert LIBRARIAN_PROMPT is not None
    assert len(LIBRARIAN_PROMPT) > 100
    assert "BibTeX" in LIBRARIAN_PROMPT


def test_figure_planner_prompt_exists():
    """Test that FIGURE_PLANNER_PROMPT is defined."""
    assert FIGURE_PLANNER_PROMPT is not None
    assert len(FIGURE_PLANNER_PROMPT) > 100
