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
    assert 'const pathname = `/workspaces/${workspaceId}/chat`;' in source
    assert 'query.set("feature", featureId);' in source
    assert 'query.set("skill", explicitSkillId);' in source


def test_legacy_feature_redirect_shell_is_removed():
    """The old /features/[featureId] redirect shell should not remain as a compatibility route."""
    repo_root = Path(__file__).resolve().parents[3]
    assert not (
        repo_root
        / "frontend"
        / "app"
        / "(workbench)"
        / "workspaces"
        / "[id]"
        / "features"
        / "[featureId]"
        / "page.tsx"
    ).exists()
