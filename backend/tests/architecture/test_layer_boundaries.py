"""Architecture guard tests - prevent business logic from leaking into routers."""

import ast
import importlib
import inspect
from pathlib import Path

import pytest


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


ROUTER_MODULES = [
    "src.gateway.routers.artifacts",
    "src.gateway.routers.references",
    "src.gateway.routers.workspaces",
]

BUSINESS_IMPORTS = {
    "src.services.credit_service",
}


class TestRouterLayerBoundaries:
    @pytest.mark.parametrize("module_name", ROUTER_MODULES)
    def test_router_does_not_import_credit_service(self, module_name: str):
        source = _get_router_source(module_name)
        imports = _get_imports(source)
        for forbidden in BUSINESS_IMPORTS:
            assert forbidden not in imports, (
                f"{module_name} imports {forbidden} — "
                "business orchestration must live in application/handlers"
            )


class TestRouterRegistration:
    def test_all_routers_registered(self):
        app_source = _get_router_source("src.gateway.app")

        expected_routers = [
            "artifacts",
            "auth",
            "capabilities",
            "compute",
            "dashboard",
            "execution_commit",
            "executions",
            "latex",
            "mcp",
            "models",
            "references",
            "runs",
            "templates",
            "thread_runs",
            "threads",
            "uploads",
            "workspace_rooms",
            "workspaces",
        ]

        for router_name in expected_routers:
            assert router_name in app_source, (
                f"Router '{router_name}' not found in app.py imports"
            )


class TestAuthDependency:
    AUTH_REQUIRED_ROUTERS = [
        "src.gateway.routers.workspaces",
        "src.gateway.routers.references",
        "src.gateway.routers.artifacts",
    ]

    @pytest.mark.parametrize("module_name", AUTH_REQUIRED_ROUTERS)
    def test_authenticated_routers_import_get_current_user(self, module_name: str):
        source = _get_router_source(module_name)
        assert "get_current_user" in source, (
            f"{module_name} does not use get_current_user"
        )


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
