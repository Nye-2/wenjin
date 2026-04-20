"""Architecture guard: feature execution must enter through domain ingress."""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).parents[2] / "src"
_ALLOWED_HANDLER_IMPORTERS = {
    "application/services/thread_feature_service.py",
    "gateway/deps/application.py",
    "application/services/feature_launch_service.py",
}
_ALLOWED_DIRECT_EXECUTE_CALLERS = {
    "application/services/feature_launch_service.py",
}


def _imports_feature_execution_handler_class(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "src.application.handlers.feature_execution_handler":
            continue
        for alias in node.names:
            if alias.name == "FeatureExecutionHandler":
                return True
    return False


def test_feature_execution_handler_imports_are_bounded() -> None:
    """Only ingress/bootstrap adapters may import FeatureExecutionHandler."""
    violations: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        rel = py_file.relative_to(_SRC_ROOT).as_posix()
        if rel == "application/handlers/feature_execution_handler.py":
            continue
        if not _imports_feature_execution_handler_class(py_file):
            continue
        if rel not in _ALLOWED_HANDLER_IMPORTERS:
            violations.append(rel)
    assert not violations, (
        "FeatureExecutionHandler imports must be constrained to ingress/bootstrap adapters:\n"
        + "\n".join(violations)
    )


def test_direct_execute_calls_go_through_ingress() -> None:
    """Direct execute() calls should only exist inside FeatureIngressService."""
    violations: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        rel = py_file.relative_to(_SRC_ROOT).as_posix()
        source = py_file.read_text()
        if "feature_execution_handler.execute(" not in source:
            continue
        if rel not in _ALLOWED_DIRECT_EXECUTE_CALLERS:
            violations.append(rel)
    assert not violations, (
        "Direct feature_execution_handler.execute(...) calls must stay in ingress:\n"
        + "\n".join(violations)
    )
