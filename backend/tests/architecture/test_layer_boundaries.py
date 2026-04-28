"""Architecture guard tests - prevent business logic from leaking into routers.

These tests inspect router source code to enforce layer boundaries defined in
docs/architecture/adr-platform-boundaries.md.

Phase 0 guard: Some tests are marked xfail because the violations exist today
and will be fixed in Phase 2 (router slimming). The guards ensure no NEW
violations are introduced.
"""

import ast
import importlib
import inspect
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_router_source(module_name: str) -> str:
    """Return the source code of a router module."""
    mod = importlib.import_module(module_name)
    return inspect.getsource(mod)


def _get_imports(source: str) -> set[str]:
    """Return the set of imported module names from source code."""
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


# ---------------------------------------------------------------------------
# Router modules that MUST NOT contain business orchestration
# ---------------------------------------------------------------------------

# These routers should be pure HTTP adapters after Phase 2.
# Phase 0 establishes the guard; violations are xfail until fixed.
ROUTER_MODULES = [
    "src.gateway.routers.papers",
    "src.gateway.routers.artifacts",
    "src.gateway.routers.workspaces",
    "src.gateway.routers.tasks",
]

# features.py currently contains orchestration (Phase 2 target)
PHASE2_ROUTER_MODULES = [
    "src.gateway.routers.features",
]

# Imports that indicate business orchestration in a router
BUSINESS_IMPORTS = {
    "src.services.credit_service",
    "src.services.literature_service",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRouterLayerBoundaries:
    """Guard tests ensuring routers stay as HTTP adapters."""

    @pytest.mark.parametrize("module_name", ROUTER_MODULES)
    def test_router_does_not_import_credit_service(self, module_name: str):
        """Routers (excluding features) must not directly import CreditService."""
        source = _get_router_source(module_name)
        imports = _get_imports(source)
        for forbidden in BUSINESS_IMPORTS:
            assert forbidden not in imports, (
                f"{module_name} imports {forbidden} — "
                "business orchestration must live in application/handlers"
            )

    @pytest.mark.parametrize("module_name", PHASE2_ROUTER_MODULES)
    def test_features_router_does_not_import_business_services(self, module_name: str):
        """features.py must not import business services (Phase 2 complete)."""
        source = _get_router_source(module_name)
        imports = _get_imports(source)
        for forbidden in BUSINESS_IMPORTS:
            assert forbidden not in imports, (
                f"{module_name} imports {forbidden} — "
                "should be moved to application/handlers in Phase 2"
            )


class TestRouterRegistration:
    """Ensure all routers are registered in the app."""

    def test_all_routers_registered(self):
        """All router modules should be imported in app.py."""
        app_source = _get_router_source("src.gateway.app")

        expected_routers = [
            "artifacts",
            "auth",
            "compute",
            "dashboard",
            "features",
            "latex",
            "literature",
            "mcp",
            "memory",
            "models",
            "papers",
            "runs",
            "skills",
            "tasks",
            "templates",
            "thread_runs",
            "threads",
            "uploads",
            "workspaces",
        ]

        for router_name in expected_routers:
            assert router_name in app_source, (
                f"Router '{router_name}' not found in app.py imports"
            )


class TestAuthDependency:
    """Guard tests for authentication dependency usage."""

    # Routers that MUST use get_current_user for mutating endpoints
    AUTH_REQUIRED_ROUTERS = [
        "src.gateway.routers.features",
        "src.gateway.routers.workspaces",
        "src.gateway.routers.tasks",
        "src.gateway.routers.papers",
        "src.gateway.routers.artifacts",
    ]

    @pytest.mark.parametrize("module_name", AUTH_REQUIRED_ROUTERS)
    def test_authenticated_routers_import_get_current_user(self, module_name: str):
        """Routers with auth requirements must import get_current_user."""
        source = _get_router_source(module_name)
        assert "get_current_user" in source, (
            f"{module_name} does not use get_current_user"
        )


# ---------------------------------------------------------------------------
# Enforce ADR-platform-boundaries: application handlers must not import HTTP layer.
# ---------------------------------------------------------------------------

_HANDLERS_DIR = Path(__file__).parents[2] / "src" / "application" / "handlers"

FORBIDDEN_MODULES = (
    "fastapi",
    "starlette",
    "src.gateway",
)


def _collect_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


def test_application_handlers_have_no_http_imports():
    """Application handlers must not import FastAPI, Starlette, or gateway deps."""
    assert _HANDLERS_DIR.is_dir(), f"Handlers directory not found: {_HANDLERS_DIR}"
    violations: list[str] = []
    for py_file in _HANDLERS_DIR.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        for module in _collect_imports(py_file):
            for forbidden in FORBIDDEN_MODULES:
                if module == forbidden or module.startswith(forbidden + "."):
                    violations.append(f"{py_file.name}: imports {module!r}")
    assert not violations, (
        "Application handlers must not import HTTP/gateway modules:\n"
        + "\n".join(violations)
    )
