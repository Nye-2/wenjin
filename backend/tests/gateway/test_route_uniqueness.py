"""Regression tests for gateway route registration."""

from collections import defaultdict


def test_gateway_has_no_duplicate_path_method_pairs():
    """Each HTTP path/method pair should map to a single route handler."""
    from src.gateway.app import app

    routes: dict[tuple[str, tuple[str, ...]], list[str]] = defaultdict(list)
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = tuple(
            sorted(
                method
                for method in getattr(route, "methods", set())
                if method not in {"HEAD", "OPTIONS"}
            )
        )
        if not path or not methods:
            continue
        routes[(path, methods)].append(route.name)

    duplicates = {
        key: names
        for key, names in routes.items()
        if len(names) > 1
    }

    assert duplicates == {}
