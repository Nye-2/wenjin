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
    "src.gateway.routers.artifacts",
    "src.gateway.routers.references",
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
            "mcp",
            "memory",
            "models",
            "references",
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
        "src.gateway.routers.references",
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


def test_reference_library_has_no_direct_agent_external_search_tools():
    """Agents must not regain direct paper-search tools outside Reference Library."""
    backend_src = Path(__file__).parents[2] / "src"
    retired_paths = [
        backend_src / "academic" / "tools" / "semantic_scholar.py",
        backend_src / "academic" / "literature" / "tools.py",
        backend_src / "academic" / "citation" / "bibtex" / "exporter.py",
        backend_src / "mcp" / "tools" / "arxiv.py",
        backend_src / "mcp" / "tools" / "pubmed.py",
        backend_src / "mcp" / "tools" / "doi.py",
    ]
    for path in retired_paths:
        assert not path.exists(), f"Retired non-SSOT tool surface still exists: {path}"

    lead_agent_source = (backend_src / "agents" / "lead_agent" / "agent.py").read_text()
    forbidden = (
        "src.academic.tools.semantic_scholar",
        "src.academic.literature.tools",
        "tools.append(search_external",
        "tools.append(semantic_scholar_search",
    )
    for marker in forbidden:
        assert marker not in lead_agent_source


def test_academic_subagents_do_not_request_direct_semantic_scholar_tool():
    """Subagents must use Reference Library navigation, not direct external search."""
    backend_src = Path(__file__).parents[2] / "src"
    for relative in (
        "subagents/academic/registry.py",
        "subagents/academic/resolver.py",
        "subagents/academic/prompts.py",
        "subagents/academic/thesis_prompts.py",
    ):
        source = (backend_src / relative).read_text()
        assert "semantic_scholar_search" not in source


def test_reference_library_bypass_tool_denylist_is_shared():
    """Lead agent and academic resolver must use the shared SSOT boundary list."""
    backend_src = Path(__file__).parents[2] / "src"
    lead_agent_source = (backend_src / "agents" / "lead_agent" / "agent.py").read_text()
    resolver_source = (backend_src / "subagents" / "academic" / "resolver.py").read_text()

    assert "is_reference_library_bypass_tool" in lead_agent_source
    assert "is_reference_library_bypass_tool" in resolver_source
    assert "_REFERENCE_LIBRARY_BYPASS_TOOL_NAMES" not in lead_agent_source
    assert "_RETIRED_ACADEMIC_SEARCH_TOOLS" not in resolver_source


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
