"""Architecture convergence guards for CI and release gate configuration."""

from __future__ import annotations

from pathlib import Path

from src.quality.release_gate import CORE_GATE_CHECKS
from src.services.release_gate_service import ReleaseGateService

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_frontend_ci_runs_static_build_and_unit_gates() -> None:
    """Frontend CI should enforce the same checks required by release docs."""
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "frontend-unit-tests.yml"
    ).read_text()

    assert "npm run typecheck" in workflow
    assert "npm run lint" in workflow
    assert "npm run build" in workflow
    assert "npm test" in workflow


def test_frontend_next_env_is_stable_for_static_build_gate() -> None:
    """Tracked Next route types should match the production build output."""
    next_env = (PROJECT_ROOT / "frontend" / "next-env.d.ts").read_text()

    assert 'import "./.next/types/routes.d.ts";' in next_env
    assert ".next/dev/types/routes.d.ts" not in next_env


def test_release_gate_includes_current_execution_architecture_checks() -> None:
    """The backend release gate should execute the converged execution UX guards."""
    required = {
        "execution_commit_writeback_security",
        "execution_resume_runtime_config",
        "execution_ux_convergence",
        "native_harness_quality_gate",
        "model_catalog_pricing_gate",
        "frontend_execution_ux_unit_tests",
        "frontend_static_build",
        "frontend_lint",
    }

    assert required.issubset(set(CORE_GATE_CHECKS))

    service = ReleaseGateService(
        project_root=PROJECT_ROOT,
        backend_root=PROJECT_ROOT / "backend",
    )
    command_by_id = {command.check_id: command.command for command in service.core_commands}

    assert "test_execution_commit_router.py" in " ".join(
        command_by_id["execution_commit_writeback_security"]
    )
    assert "test_thread_turn_handler.py" in " ".join(
        command_by_id["execution_resume_runtime_config"]
    )
    assert "tests/unit/lib/execution-run-view.test.ts" in " ".join(
        command_by_id["frontend_execution_ux_unit_tests"]
    )
    assert "src.quality.model_catalog_pricing_gate" in " ".join(
        command_by_id["model_catalog_pricing_gate"]
    )
    harness_command = " ".join(command_by_id["native_harness_quality_gate"])
    assert "tests/agents/harness/test_scheduler_and_python_tool.py" in harness_command
    assert "tests/agents/harness/test_sandbox_file_tools.py" in harness_command
    assert "tests/agents/harness/test_command_audit.py" in harness_command
    assert "tests/agents/harness/test_policy_and_registry.py" in harness_command
    assert "tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py" in harness_command
    assert "tests/agents/harness/test_research_task_eval.py" in harness_command
    assert "tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py" in harness_command
    assert "tests/agents/harness/test_context_assembly.py" in harness_command
    assert "tests/unit/subagents/test_react.py" in harness_command
    assert "tests/subagents/v2/test_registry.py" in harness_command
    assert "tests/agents/lead_agent/v2/test_team_policy.py" in harness_command
    assert "tests/agents/lead_agent/v2/test_sandbox_runtime.py" in harness_command
    assert "test_run_session_prism_review_items_satisfy_writing_evidence_eval" in harness_command
    assert "tests/agents/lead_agent/v2/test_citation_source_audit.py" in harness_command
    assert "test_surface_projection_includes_review_provenance_and_protection" in harness_command
    assert "tests/services/test_prism_review_projection.py" in harness_command
    assert "tests/architecture/test_native_harness_boundaries.py" in harness_command
    assert "tests/dataservice/test_sandbox_domain.py" in harness_command
    assert "tests/integration/test_harness_mock_sandbox_e2e.py" in harness_command
