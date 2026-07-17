"""Architecture guard tests - prevent business logic from leaking into routers."""

import ast
import importlib
import inspect
import subprocess
import sys
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
            "dashboard",
            "latex",
            "missions",
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

        for removed_router in ("capabilities", "execution_commit", "executions"):
            assert f"{removed_router}.router" not in app_source


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


@pytest.mark.parametrize(
    ("relative_root", "forbidden"),
    [
        ("agents/workspace_agent", ("src.agents.lead_agent", "src.execution", "src.gateway")),
        ("mission_runtime", ("src.agents.lead_agent", "src.execution", "fastapi", "src.gateway")),
        ("tools/orchestrator", ("src.execution", "fastapi", "src.gateway")),
        ("review_commit_runtime", ("src.execution", "fastapi", "src.gateway")),
    ],
)
def test_mission_runtime_layers_do_not_depend_on_removed_or_http_layers(
    relative_root: str,
    forbidden: tuple[str, ...],
) -> None:
    root = Path(__file__).parents[2] / "src" / relative_root
    assert root.is_dir()
    violations: list[str] = []
    for path in root.rglob("*.py"):
        for imported in _collect_imports(path):
            if any(imported == item or imported.startswith(item + ".") for item in forbidden):
                violations.append(f"{path.relative_to(root)}: imports {imported}")
    assert not violations, "Mission architecture boundary violations:\n" + "\n".join(violations)


def test_mission_policy_contract_is_framework_independent() -> None:
    path = Path(__file__).parents[2] / "src" / "contracts" / "mission_policy.py"
    imports = _collect_imports(path)
    assert not any(
        imported.startswith(("fastapi", "sqlalchemy", "src.gateway", "src.database"))
        for imported in imports
    )


def test_mission_production_composition_imports_in_fresh_interpreter() -> None:
    backend_root = Path(__file__).parents[2]
    completed = subprocess.run(
        [sys.executable, "-c", "import src.mission_runtime.production"],
        cwd=backend_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
