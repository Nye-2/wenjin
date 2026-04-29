"""Architecture guard: feature execution must enter through domain ingress."""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).parents[2] / "src"
_ALLOWED_SUBMISSION_SERVICE_IMPORTERS = {
    "application/services/feature_ingress_factory.py",
    "application/services/feature_launch_service.py",
}
_ALLOWED_DIRECT_EXECUTE_CALLERS = {
    "application/services/feature_launch_service.py",
}


def _imports_feature_submission_service_class(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "src.application.services.feature_submission_service":
            continue
        for alias in node.names:
            if alias.name == "FeatureSubmissionService":
                return True
    return False


def test_feature_submission_service_imports_are_bounded() -> None:
    """Only ingress/bootstrap adapters may import FeatureSubmissionService."""
    violations: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        rel = py_file.relative_to(_SRC_ROOT).as_posix()
        if rel == "application/services/feature_submission_service.py":
            continue
        if not _imports_feature_submission_service_class(py_file):
            continue
        if rel not in _ALLOWED_SUBMISSION_SERVICE_IMPORTERS:
            violations.append(rel)
    assert not violations, (
        "FeatureSubmissionService imports must be constrained to ingress/bootstrap adapters:\n"
        + "\n".join(violations)
    )


def test_direct_execute_calls_go_through_ingress() -> None:
    """Direct execute() calls should only exist inside FeatureIngressService."""
    violations: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        rel = py_file.relative_to(_SRC_ROOT).as_posix()
        source = py_file.read_text()
        if "feature_submission_service.execute(" not in source:
            continue
        if rel not in _ALLOWED_DIRECT_EXECUTE_CALLERS:
            violations.append(rel)
    assert not violations, (
        "Direct feature_submission_service.execute(...) calls must stay in ingress:\n"
        + "\n".join(violations)
    )


def test_feature_ingress_launch_accepts_command_object_only() -> None:
    """Launch/resume input should stay consolidated in FeatureLaunchCommand."""
    path = _SRC_ROOT / "application/services/feature_launch_service.py"
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "launch":
            continue
        args = [arg.arg for arg in node.args.args]
        assert args == ["self", "command"]
        annotation = node.args.args[1].annotation
        assert isinstance(annotation, ast.Name)
        assert annotation.id == "FeatureLaunchCommand"
        return
    raise AssertionError("FeatureIngressService.launch was not found")


def test_gateway_does_not_export_feature_submission_service_factory() -> None:
    """Gateway deps should expose the ingress dependency, not its inner service."""
    violations: list[str] = []
    for rel in (
        "gateway/deps/__init__.py",
        "gateway/deps/application.py",
    ):
        source = (_SRC_ROOT / rel).read_text()
        if "get_feature_submission_service" in source:
            violations.append(rel)
    assert not violations, (
        "Gateway dependency exports must not expose FeatureSubmissionService directly:\n"
        + "\n".join(violations)
    )


def test_legacy_feature_execution_handler_module_is_removed() -> None:
    """Feature submission no longer belongs in application.handlers."""
    assert not (_SRC_ROOT / "application/handlers/feature_execution_handler.py").exists()
