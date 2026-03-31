"""Cross-layer consistency tests for workspace feature frontend routes."""

import re
from pathlib import Path

from src.workspace_features import iter_workspace_features


def _frontend_workspace_page_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return (
        repo_root
        / "frontend"
        / "app"
        / "(workbench)"
        / "workspaces"
        / "[id]"
        / "page.tsx"
    )


def _frontend_route_map_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return (
        repo_root
        / "frontend"
        / "lib"
        / "workspace-feature-routes.ts"
    )


def _parse_feature_skill_map(source: str) -> dict[str, str | None]:
    match = re.search(
        r"export const workspaceFeatureSkillMap: Record<string, string \| null> = \{(?P<body>.*?)\n\};",
        source,
        re.DOTALL,
    )
    assert match is not None, "Cannot locate workspaceFeatureSkillMap in frontend route map file"

    body = match.group("body")
    pairs = re.findall(
        r'^\s*([a-z_]+)\s*:\s*(null|"([a-z-]+)"),\s*$',
        body,
        re.MULTILINE,
    )
    return {
        feature_id: (skill_id or None)
        for feature_id, _, skill_id in pairs
    }


def test_frontend_feature_route_map_matches_registry():
    """All registry features should have a frontend route helper entry, without extras."""
    route_map_path = _frontend_route_map_path()
    source = route_map_path.read_text(encoding="utf-8")
    route_map = _parse_feature_skill_map(source)

    declared_feature_ids = {feature.id for feature in iter_workspace_features()}
    mapped_feature_ids = set(route_map.keys())

    missing_feature_ids = sorted(declared_feature_ids - mapped_feature_ids)
    extra_feature_ids = sorted(mapped_feature_ids - declared_feature_ids)

    assert missing_feature_ids == [], (
        "Frontend route map is missing feature ids: " + ", ".join(missing_feature_ids)
    )
    assert extra_feature_ids == [], (
        "Frontend route map has unknown feature ids: " + ", ".join(extra_feature_ids)
    )


def test_frontend_feature_routes_target_canonical_chat_entry():
    """Feature navigation should resolve to the canonical workspace chat entry."""
    route_map_path = _frontend_route_map_path()
    source = route_map_path.read_text(encoding="utf-8")
    assert 'const pathname = `/workspaces/${workspaceId}/chat/new`;' in source
    assert 'query.set("feature", featureId);' in source
    assert "resolveWorkspaceFeatureSkillId(" in source
