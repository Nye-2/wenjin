"""Tests for thesis workspace capability data in the capabilities table."""

THESIS_CAPABILITY_IDS = [
    "deep_research",
    "figure_generation",
    "literature_management",
    "opening_research",
    "outline_generate",
    "section_revise",
    "section_write",
]


def test_thesis_capability_ids_are_defined():
    """Thesis workspace should have 7 capabilities covering the core workflow."""
    assert len(THESIS_CAPABILITY_IDS) == 7
    assert THESIS_CAPABILITY_IDS[0] == "deep_research"
    assert THESIS_CAPABILITY_IDS[-1] == "section_write"
