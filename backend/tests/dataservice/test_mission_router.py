"""Route-surface tests for the internal Mission DataService API."""

from src.dataservice_app.routers.mission import router


def test_mission_router_exposes_runtime_store_operations() -> None:
    paths = {route.path for route in router.routes}
    assert {
        "/internal/v1/missions",
        "/internal/v1/missions/{mission_id}",
        "/internal/v1/workspaces/{workspace_id}/missions",
        "/internal/v1/missions/{mission_id}/items/append",
        "/internal/v1/missions/{mission_id}/checkpoint",
        "/internal/v1/missions/{mission_id}/commands",
        "/internal/v1/missions/{mission_id}/commands/apply",
        "/internal/v1/missions/{mission_id}/lease/claim",
        "/internal/v1/missions/{mission_id}/review-items",
        "/internal/v1/missions/{mission_id}/review-decisions",
        "/internal/v1/missions/{mission_id}/commits",
    } <= paths


def test_mission_history_route_exposes_only_opaque_cursor() -> None:
    route = next(
        item
        for item in router.routes
        if item.path == "/internal/v1/workspaces/{workspace_id}/missions"
    )
    query_names = {parameter.name for parameter in route.dependant.query_params}

    assert "cursor" in query_names
    assert "before_updated_at" not in query_names
    assert "before_mission_id" not in query_names
