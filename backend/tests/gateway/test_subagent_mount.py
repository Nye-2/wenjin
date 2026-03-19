"""Regression tests for gateway-mounted subagent routes."""


def test_gateway_mounts_subagent_routes_under_api_prefix():
    """Subagent API should be reachable through the main gateway app."""
    from src.gateway.app import app

    paths = {route.path for route in app.routes if getattr(route, "path", None)}

    assert "/api/subagents/events" in paths
    assert "/api/subagents/threads/{thread_id}/spawn" in paths
