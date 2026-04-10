"""Cross-layer consistency tests for workspace feature frontend routes."""

from pathlib import Path


def _frontend_route_map_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return (
        repo_root
        / "frontend"
        / "lib"
        / "workspace-feature-routes.ts"
    )


def _frontend_feature_redirect_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return (
        repo_root
        / "frontend"
        / "app"
        / "(workbench)"
        / "workspaces"
        / "[id]"
        / "features"
        / "[featureId]"
        / "page.tsx"
    )


def test_frontend_feature_routes_do_not_hardcode_default_skill_map():
    """Default feature skills should come from API metadata, not a frontend map."""
    route_map_path = _frontend_route_map_path()
    source = route_map_path.read_text(encoding="utf-8")
    assert "workspaceFeatureSkillMap" not in source
    assert "resolveWorkspaceFeatureSkillId" not in source


def test_frontend_feature_routes_target_canonical_chat_entry():
    """Feature navigation should resolve to the canonical workspace chat entry."""
    route_map_path = _frontend_route_map_path()
    source = route_map_path.read_text(encoding="utf-8")
    redirect_source = _frontend_feature_redirect_path().read_text(encoding="utf-8")
    assert 'const pathname = `/workspaces/${workspaceId}/chat`;' in source
    assert 'query.set("feature", featureId);' in source
    assert 'query.set("skill", explicitSkillId);' in source
    assert "feature.defaultSkillId" in redirect_source
    assert "useFeaturesStore" in redirect_source
