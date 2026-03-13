"""Cross-layer consistency tests for workspace feature frontend routes."""

from pathlib import Path
import re

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


def _parse_feature_route_map(source: str) -> dict[str, str]:
    match = re.search(
        r"const featureRouteMap: Record<string, string> = \{(?P<body>.*?)\n\};",
        source,
        re.DOTALL,
    )
    assert match is not None, "Cannot locate featureRouteMap in frontend workspace page"

    body = match.group("body")
    pairs = re.findall(
        r'^\s*([a-z_]+)\s*:\s*"([a-z-]+)",\s*$',
        body,
        re.MULTILINE,
    )
    return {feature_id: route for feature_id, route in pairs}


def test_frontend_feature_route_map_matches_registry():
    """All registry features should have a frontend route map entry, without extras."""
    page_path = _frontend_workspace_page_path()
    source = page_path.read_text(encoding="utf-8")
    route_map = _parse_feature_route_map(source)

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


def test_frontend_feature_route_pages_exist():
    """Every route declared in featureRouteMap should point to an existing page file."""
    page_path = _frontend_workspace_page_path()
    workspace_dir = page_path.parent
    source = page_path.read_text(encoding="utf-8")
    route_map = _parse_feature_route_map(source)

    missing_pages: list[str] = []
    for route in sorted(set(route_map.values())):
        route_page = workspace_dir / route / "page.tsx"
        if not route_page.exists():
            missing_pages.append(route)

    assert missing_pages == [], (
        "Missing frontend page.tsx for routes: " + ", ".join(missing_pages)
    )
