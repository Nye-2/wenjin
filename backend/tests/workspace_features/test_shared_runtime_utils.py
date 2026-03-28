"""Shared runtime utilities: _emit_bound_runtime must have single canonical source."""

import ast
from pathlib import Path


SERVICES_DIR = Path(__file__).parents[2] / "src" / "workspace_features" / "services"
GRAPHS_DIR = Path(__file__).parents[2] / "src" / "agents" / "graphs"


def _defines_emit_bound_runtime(path: Path) -> bool:
    """Return True if the file defines _emit_bound_runtime itself (not imports it)."""
    tree = ast.parse(path.read_text())
    return any(
        isinstance(node, ast.AsyncFunctionDef) and node.name == "_emit_bound_runtime"
        for node in ast.walk(tree)
    )


def test_no_service_defines_emit_bound_runtime():
    """workspace_features/services must not define _emit_bound_runtime locally."""
    offenders = [
        str(p.relative_to(Path(__file__).parents[2] / "src"))
        for p in SERVICES_DIR.rglob("*.py")
        if _defines_emit_bound_runtime(p)
    ]
    assert not offenders, (
        "_emit_bound_runtime must be imported from task.runtime_blocks, not redefined:\n"
        + "\n".join(offenders)
    )


def test_no_graph_defines_emit_bound_runtime():
    """agents/graphs must not define _emit_bound_runtime locally."""
    offenders = [
        str(p.relative_to(Path(__file__).parents[2] / "src"))
        for p in GRAPHS_DIR.rglob("*.py")
        if _defines_emit_bound_runtime(p)
    ]
    assert not offenders, (
        "_emit_bound_runtime must be imported from task.runtime_blocks, not redefined:\n"
        + "\n".join(offenders)
    )


def test_emit_bound_runtime_is_exported_from_runtime_blocks():
    """emit_bound_runtime must be importable from task.runtime_blocks."""
    import inspect

    from src.task.runtime_blocks import emit_bound_runtime

    assert inspect.iscoroutinefunction(emit_bound_runtime)
