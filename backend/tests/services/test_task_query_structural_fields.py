"""Verify task queries use structural columns, not JSONB path queries."""

from pathlib import Path

# Current owners of auxiliary task structural fields.
_TARGET_FILES = [
    Path(__file__).parents[2] / "src" / "dataservice" / "domains" / "task" / "repository.py",
    Path(__file__).parents[2] / "src" / "dataservice" / "domains" / "task" / "service.py",
    Path(__file__).parents[2] / "src" / "task" / "service.py",
    Path(__file__).parents[2] / "src" / "task" / "store.py",
]

# Patterns that indicate JSONB path queries (any of these in a non-comment line is a violation)
_JSONB_FIELD_PATTERNS = [
    'payload["workspace_id"]',
    "payload['workspace_id']",
    'payload["thread_id"]',
    "payload['thread_id']",
]


def _find_violations(path: Path) -> list[str]:
    violations = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pattern in _JSONB_FIELD_PATTERNS:
            if pattern in stripped:
                violations.append(f"{path.name}:{i}: {stripped}")
                break
    return violations


def test_no_jsonb_path_queries_for_structural_fields():
    """Target files must use column filters, not JSONB path queries for structural fields."""
    all_violations = []
    for path in _TARGET_FILES:
        assert path.is_file(), f"File not found: {path}"
        all_violations.extend(_find_violations(path))
    assert not all_violations, (
        "JSONB path queries found for fields that have first-class columns:\n"
        + "\n".join(all_violations)
    )
