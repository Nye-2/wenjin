"""Tests for thesis workspace capability data in the capabilities table."""

THESIS_CAPABILITY_IDS = [
    "idea_to_thesis_manuscript",
    "thesis_research_pack",
    "thesis_empirical_analysis",
    "thesis_revision_pass",
    "thesis_defense_pack",
    "thesis_reference_curation",
]


def test_thesis_capability_ids_are_defined():
    """Thesis workspace should expose mission-level Super Agent capabilities."""
    assert len(THESIS_CAPABILITY_IDS) == 6
    assert THESIS_CAPABILITY_IDS[0] == "idea_to_thesis_manuscript"
    assert THESIS_CAPABILITY_IDS[-1] == "thesis_reference_curation"
