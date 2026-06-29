"""Tests that the old user-facing memory router is hidden."""

from src.gateway.app import app


def test_memory_router_is_not_mounted_in_gateway_app() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/memory" not in paths
    assert "/api/memory/status" not in paths
