from src.gateway.routers.missions import router


def test_public_mission_router_exposes_view_trace_review_commit_and_permission() -> None:
    routes = {(route.path, next(iter(route.methods))) for route in router.routes}
    paths = {path for path, _ in routes}

    assert "/missions/{mission_id}" in paths
    assert "/workspaces/{workspace_id}/missions" in paths
    assert "/workspaces/{workspace_id}/missions/events" in paths
    assert "/missions/{mission_id}/items" in paths
    assert "/missions/{mission_id}/actions" in paths
    assert "/missions/{mission_id}/review-decisions" in paths
    assert "/missions/{mission_id}/commits" in paths
    assert "/missions/{mission_id}/permissions/{request_id}/resolve" in paths
    assert all("execution" not in path for path in paths)
