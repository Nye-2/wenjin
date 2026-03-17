"""Release gate evaluator for five-workspace production launch."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

CORE_GATE_CHECKS: tuple[str, ...] = (
    "thesis_output_language_zh",
    "sci_output_language_en",
    "workspace_e2e_matrix",
    "features_router_regression",
    "feature_execution_handler_regression",
    "five_workspace_smoke",
    "executor_dual_mode",
    "frontend_typescript_check",
)

EXTENDED_GATE_CHECKS: tuple[str, ...] = (
    "integration_tool_chain",
    "mcp_academic_tools",
    "integration_http_client",
)

CHECK_DESCRIPTIONS: Mapping[str, str] = {
    "thesis_output_language_zh": "Verify thesis workspace output language is fixed to zh.",
    "sci_output_language_en": "Verify sci workspace output language is fixed to en.",
    "workspace_e2e_matrix": "Run workspace e2e matrix tests.",
    "features_router_regression": "Run features router regression tests.",
    "feature_execution_handler_regression": "Run feature execution handler regression tests.",
    "five_workspace_smoke": "Run five-workspace smoke tests (one end-to-end path per workspace type).",
    "executor_dual_mode": "Run dual-mode executor tests (Celery + local asyncio).",
    "frontend_typescript_check": "Run frontend TypeScript compile check.",
    "integration_tool_chain": "Run integration test for tool chain.",
    "mcp_academic_tools": "Run MCP academic tools integration tests.",
    "integration_http_client": "Run HTTP client integration tests.",
}

CHECK_FIX_HINTS: Mapping[str, str] = {
    "thesis_output_language_zh": "Re-check thesis service/handler payload output_language='zh' enforcement and rerun workspace matrix tests.",
    "sci_output_language_en": "Re-check sci service/handler payload output_language='en' enforcement and rerun workspace matrix tests.",
    "workspace_e2e_matrix": "Run `PYTHONPATH=. uv run pytest tests/workspace_features/test_workspace_e2e_matrix.py -q` and fix failing workspace behavior.",
    "features_router_regression": "Run `PYTHONPATH=. uv run pytest tests/gateway/routers/test_features.py -q` and align response contracts.",
    "feature_execution_handler_regression": "Run `PYTHONPATH=. uv run pytest tests/application/handlers/test_feature_execution_handler.py -q` and fix task lifecycle regressions.",
    "five_workspace_smoke": "Run `PYTHONPATH=. uv run pytest tests/workspace_features/test_five_workspace_smoke.py -q` and fix workspace smoke failures.",
    "executor_dual_mode": "Run `PYTHONPATH=. uv run pytest tests/task/test_executor.py tests/task/test_service_executor.py -q` and fix executor regressions.",
    "frontend_typescript_check": "Run `cd frontend && npx tsc --noEmit` and resolve TypeScript errors.",
    "integration_tool_chain": "Run `PYTHONPATH=. uv run pytest tests/integration/test_tool_chain.py -q` and fix external chain regressions.",
    "mcp_academic_tools": "Run `PYTHONPATH=. uv run pytest tests/mcp/test_academic_tools.py -q` and fix MCP tool adapters.",
    "integration_http_client": "Run `PYTHONPATH=. uv run pytest tests/integration/test_http_client.py -q` and fix HTTP integration issues.",
}


def _evaluate_gate(
    check_ids: tuple[str, ...],
    results: Mapping[str, bool] | None,
    *,
    missing_as_failed: bool,
) -> dict[str, Any]:
    normalized_results: Mapping[str, bool] = results or {}
    checks: list[dict[str, str]] = []
    passed = 0
    failed = 0
    missing = 0

    for check_id in check_ids:
        raw = normalized_results.get(check_id)
        if raw is True:
            status = "passed"
            passed += 1
        elif raw is False:
            status = "failed"
            failed += 1
        else:
            status = "missing"
            missing += 1
            if missing_as_failed:
                failed += 1

        checks.append(
            {
                "id": check_id,
                "status": status,
                "description": CHECK_DESCRIPTIONS.get(check_id, ""),
                "fix_hint": CHECK_FIX_HINTS.get(check_id, ""),
            }
        )

    if failed > 0:
        gate_status = "failed"
    elif missing > 0:
        gate_status = "pending"
    else:
        gate_status = "passed"

    return {
        "status": gate_status,
        "total": len(check_ids),
        "passed": passed,
        "failed": failed,
        "missing": missing,
        "checks": checks,
    }


def evaluate_release_gate(
    *,
    core_results: Mapping[str, bool],
    extended_results: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Build a release readiness report.

    Core gate is strict and missing checks are treated as failures.
    Extended gate is advisory and does not block Go/No-Go when core passes.
    """

    core_gate = _evaluate_gate(
        CORE_GATE_CHECKS,
        core_results,
        missing_as_failed=True,
    )
    extended_gate = _evaluate_gate(
        EXTENDED_GATE_CHECKS,
        extended_results,
        missing_as_failed=False,
    )

    core_failed_checks = [
        check for check in core_gate["checks"] if check["status"] in {"failed", "missing"}
    ]
    extended_failed_checks = [
        check for check in extended_gate["checks"] if check["status"] == "failed"
    ]

    recommendations: list[str] = []
    for check in core_failed_checks:
        recommendations.append(f"[core] {check['id']}: {check['fix_hint']}")
    for check in extended_failed_checks:
        recommendations.append(f"[extended] {check['id']}: {check['fix_hint']}")
    if extended_gate["status"] == "pending":
        recommendations.append(
            "[extended] Run extended integration checks after parallel streams stabilize."
        )

    status = "passed" if core_gate["status"] == "passed" else "failed"
    go_no_go = "go" if status == "passed" else "no-go"

    return {
        "status": status,
        "go_no_go": go_no_go,
        "core_gate": core_gate,
        "extended_gate": extended_gate,
        "generated_at": datetime.now(UTC).isoformat(),
        "recommendations": recommendations,
    }
