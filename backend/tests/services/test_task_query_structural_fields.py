"""Verify task queries use structural columns, not JSONB path queries."""

from pathlib import Path


def _find_jsonb_path_queries(path: Path) -> list[str]:
    """Find payload["field"] query patterns in source."""
    source = path.read_text()
    matches = []
    for i, line in enumerate(source.splitlines(), 1):
        if 'payload["workspace_id"]' in line or 'payload["feature_id"]' in line:
            if ".as_string()" in line or ".as_integer()" in line:
                matches.append(f"{path.name}:{i}: {line.strip()}")
    return matches


def test_dashboard_shared_uses_column_filters():
    path = Path(__file__).parents[2] / "src" / "services" / "dashboard" / "shared.py"
    violations = _find_jsonb_path_queries(path)
    assert not violations, "Still using JSONB path queries:\n" + "\n".join(violations)


def test_workspace_activity_uses_column_filters():
    path = Path(__file__).parents[2] / "src" / "services" / "workspace_activity_service.py"
    violations = _find_jsonb_path_queries(path)
    assert not violations, "Still using JSONB path queries:\n" + "\n".join(violations)
