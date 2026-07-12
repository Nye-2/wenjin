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


def test_frontend_next_env_references_generated_route_types() -> None:
    """Next may emit development or production route types between commands."""
    next_env = (PROJECT_ROOT / "frontend" / "next-env.d.ts").read_text()

    assert (
        'import "./.next/types/routes.d.ts";' in next_env
        or 'import "./.next/dev/types/routes.d.ts";' in next_env
    )


def test_release_gate_includes_current_mission_architecture_checks() -> None:
    """The release gate must execute every Mission architecture owner."""
    required = {
        "mission_store",
        "mission_runtime",
        "workspace_agent",
        "subagent_runtime",
        "tool_orchestrator",
        "model_capability",
        "sandbox_security",
        "review_commit",
        "mission_cutover",
        "frontend_mission",
        "frontend_typecheck",
    }

    assert required.issubset(set(CORE_GATE_CHECKS))

    service = ReleaseGateService(
        project_root=PROJECT_ROOT,
        backend_root=PROJECT_ROOT / "backend",
    )
    command_by_id = {command.check_id: command.command for command in service.core_commands}

    assert "tests/dataservice/test_mission_store.py" in " ".join(command_by_id["mission_store"])
    assert "tests/mission_runtime" in " ".join(command_by_id["mission_runtime"])
    assert "tests/subagent_runtime" in " ".join(command_by_id["subagent_runtime"])
    assert "tests/tools/test_tool_orchestrator.py" in " ".join(command_by_id["tool_orchestrator"])
    assert "src.quality.mission_cutover_gate" in " ".join(command_by_id["mission_cutover"])
    assert "tests/unit/v2/MissionConsole.test.tsx" in " ".join(command_by_id["frontend_mission"])
