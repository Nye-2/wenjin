from src.artifacts.types import ArtifactType


def test_new_artifact_types_exist():
    assert ArtifactType.DEEP_RESEARCH_REPORT == "deep_research_report"
    assert ArtifactType.OPENING_REPORT == "opening_report"
    assert ArtifactType.FEASIBILITY_ANALYSIS == "feasibility_analysis"
    assert ArtifactType.LITERATURE_INVENTORY == "literature_inventory"
    assert ArtifactType.THESIS_CHAPTER == "thesis_chapter"
    assert ArtifactType.GAP_ANALYSIS == "gap_analysis"


def test_all_thesis_artifact_types_present():
    """Verify all artifact types needed by thesis modules exist."""
    required = {
        "framework_outline", "thesis_chapter", "figure", "paper_draft",
        "opening_report", "feasibility_analysis", "literature_review",
        "literature_inventory",
        "deep_research_report", "research_ideas", "literature_search_results", "gap_analysis",
    }
    existing = {t.value for t in ArtifactType}
    assert required.issubset(existing), f"Missing: {required - existing}"
