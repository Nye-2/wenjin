"""Documentation consistency checks for the workspace feature catalog."""

from __future__ import annotations

import re
from pathlib import Path

from src.workspace_features import CANONICAL_WORKSPACE_TYPES, iter_workspace_features, list_workspace_features

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "docs" / "product" / "workspace-feature-catalog.md"

WORKSPACE_SECTION_LABELS = {
    "thesis": "Thesis",
    "sci": "SCI",
    "proposal": "Proposal",
    "software_copyright": "Software Copyright",
    "patent": "Patent",
}


def _catalog_text() -> str:
    return CATALOG_PATH.read_text(encoding="utf-8")


def test_workspace_feature_catalog_total_count_matches_registry() -> None:
    content = _catalog_text()
    match = re.search(r"总计:\s*(\d+)\s*个 workspace 类型，\s*(\d+)\s*个 feature。", content)
    assert match is not None, "Catalog total-count line not found"

    documented_workspace_types = int(match.group(1))
    documented_feature_count = int(match.group(2))

    assert documented_workspace_types == len(CANONICAL_WORKSPACE_TYPES)
    assert documented_feature_count == len(tuple(iter_workspace_features()))


def test_workspace_feature_catalog_section_counts_match_registry() -> None:
    content = _catalog_text()

    missing_sections: list[str] = []
    mismatched_sections: list[str] = []

    for workspace_type in CANONICAL_WORKSPACE_TYPES:
        label = WORKSPACE_SECTION_LABELS[workspace_type]
        match = re.search(rf"###\s+2\.\d+\s+{re.escape(label)}\s+\((\d+)\)", content)
        if match is None:
            missing_sections.append(workspace_type)
            continue

        documented_count = int(match.group(1))
        actual_count = len(list_workspace_features(workspace_type))
        if documented_count != actual_count:
            mismatched_sections.append(
                f"{workspace_type}: documented={documented_count}, actual={actual_count}"
            )

    assert not missing_sections, f"Missing workspace sections in catalog: {missing_sections}"
    assert not mismatched_sections, (
        "Catalog workspace counts do not match registry: " + "; ".join(mismatched_sections)
    )


def test_workspace_feature_catalog_lists_all_feature_ids() -> None:
    content = _catalog_text()
    missing_feature_ids = [
        feature.id
        for feature in iter_workspace_features()
        if f"`{feature.id}`" not in content
    ]

    assert not missing_feature_ids, (
        "Catalog is missing feature ids: " + ", ".join(missing_feature_ids)
    )
