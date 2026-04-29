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
    assert not violations, "FeatureSubmissionService imports must be constrained to ingress/bootstrap adapters:\n" + "\n".join(violations)


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
    assert not violations, "Direct feature_submission_service.execute(...) calls must stay in ingress:\n" + "\n".join(violations)


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
    assert not violations, "Gateway dependency exports must not expose FeatureSubmissionService directly:\n" + "\n".join(violations)


def test_legacy_feature_execution_handler_module_is_removed() -> None:
    """Feature submission no longer belongs in application.handlers."""
    assert not (_SRC_ROOT / "application/handlers/feature_execution_handler.py").exists()


def test_legacy_workspace_lead_agent_module_is_removed() -> None:
    """Feature graph dispatch belongs under feature_leader, not chat lead-agent naming."""
    assert not (_SRC_ROOT / "agents/workspace_lead_agent.py").exists()

    violations: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        rel = py_file.relative_to(_SRC_ROOT).as_posix()
        if "src.agents.workspace_lead_agent" in py_file.read_text():
            violations.append(rel)
    assert not violations, "Feature graph imports must use src.agents.feature_leader.graph_registry:\n" + "\n".join(violations)


def test_chat_feature_routing_uses_thread_intent_router_ssot() -> None:
    """ChatTurnRouter must stay a thin adapter over the canonical intent router."""
    source = (_SRC_ROOT / "application/handlers/chat_turn_router.py").read_text()
    assert "ThreadIntentRouter.route" in source
    assert "metadata.orchestration.intent" not in source


def test_workspace_skill_catalog_is_owned_by_workspace_features() -> None:
    """Production code must not import the compatibility lead-agent skill path."""
    assert not (_SRC_ROOT / "agents/lead_agent/thread_skill_catalog.py").exists()
    assert not (_SRC_ROOT / "agents/lead_agent/thread_feature_catalog.py").exists()

    violations: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        rel = py_file.relative_to(_SRC_ROOT).as_posix()
        source = py_file.read_text()
        if (
            "src.agents.lead_agent.thread_skill_catalog" in source
            or "src.agents.lead_agent.thread_feature_catalog" in source
        ):
            violations.append(rel)
    assert not violations, (
        "Workspace feature/skill catalog imports must use src.workspace_features:\n"
        + "\n".join(violations)
    )


def test_feature_graph_modules_are_derived_from_feature_registry() -> None:
    """Graph loading must not reintroduce a second workspace-feature map."""
    source = (_SRC_ROOT / "agents/feature_leader/graph_registry.py").read_text()
    assert "_WORKSPACE_GRAPH_MODULES" not in source
    assert "_SHARED_FEATURE_GRAPH_MODULES" not in source
    assert "list_workspace_features" in source
    assert "feature.graph_module" in source
    assert "_workspace_graph_modules" in source


def test_feature_runtime_profile_is_consumed_by_feature_leader() -> None:
    """Runtime profile must be an execution policy, not only registry metadata."""
    runtime_source = (_SRC_ROOT / "agents/feature_leader/runtime.py").read_text()
    workflow_source = (_SRC_ROOT / "agents/feature_leader/workflow.py").read_text()
    assert "get_feature_runtime_profile" in runtime_source
    assert "validate_workflow_plan_against_profile" in runtime_source
    assert "agent_harness_provider" in runtime_source
    assert "validate_workflow_plan_against_profile" in workflow_source


def test_billing_policy_is_not_owned_by_feature_registry() -> None:
    """Billing must stay in services.billing_policy, not feature definitions."""
    assert not (_SRC_ROOT / "services/feature_credit_policy.py").exists()

    registry_source = (_SRC_ROOT / "workspace_features/registry.py").read_text()
    assert "credit_cost" not in registry_source

    billing_source = (_SRC_ROOT / "services/billing_policy.py").read_text()
    assert "feature_token_billing" in billing_source
    assert "thread_token_billing" in billing_source
