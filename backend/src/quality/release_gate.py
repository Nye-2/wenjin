"""Release gate evaluator for five-workspace production launch."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

CORE_GATE_CHECKS: tuple[str, ...] = (
    "thesis_output_language_zh",
    "sci_output_language_en",
    "workspace_e2e_matrix",
    "feature_submission_service_regression",
    "executor_dual_mode",
    "observability_sentry",
    "observability_prometheus",
    "agent_status_tracking",
    "workspace_lock",
    "task_metrics",
    "semantic_scholar_reference_search",
    "reference_upload_preprocess",
    "artifact_refresh_workflow",
    "artifact_followup_workflow",
    "reference_writing_workflow",
    "prism_review_workflow",
    "sci_reference_search",
    "auth_email_workflow",
    "frontend_typescript_check",
)

EXTENDED_GATE_CHECKS: tuple[str, ...] = (
    "integration_tool_chain",
    "mcp_runtime",
    "integration_http_client",
)

CHECK_DESCRIPTIONS: Mapping[str, str] = {
    "thesis_output_language_zh": "Verify thesis workspace output language is fixed to zh.",
    "sci_output_language_en": "Verify sci workspace output language is fixed to en.",
    "workspace_e2e_matrix": "Run workspace e2e matrix tests.",
    "feature_submission_service_regression": "Run feature submission service regression tests.",
    "executor_dual_mode": "Run dual-mode executor tests (Celery + local asyncio).",
    "observability_sentry": "Run Sentry observability configuration tests.",
    "observability_prometheus": "Run Prometheus metrics observability tests.",
    "agent_status_tracking": "Run agent status tracking tests.",
    "workspace_lock": "Run workspace feature submission lock tests.",
    "task_metrics": "Run task metrics tests.",
    "semantic_scholar_reference_search": "Run Semantic Scholar reference search tests.",
    "reference_upload_preprocess": "Run reference upload and document preprocess tests.",
    "artifact_refresh_workflow": "Run artifact persistence, workspace refresh, and frontend artifact reload contract tests.",
    "artifact_followup_workflow": "Run artifact open, follow-up, and rerun seed workflow gate tests.",
    "reference_writing_workflow": "Run Reference Library evidence, usage, BibTeX, and Prism workflow gate tests.",
    "prism_review_workflow": "Run Prism pending-review, file-change, and compute projection workflow gate tests.",
    "sci_reference_search": "Run SCI reference search feature service tests.",
    "auth_email_workflow": "Run auth registration, email verification code, and frontend auth flow contract tests.",
    "frontend_typescript_check": "Run frontend TypeScript compile check.",
    "integration_tool_chain": "Run integration test for tool chain.",
    "mcp_runtime": "Run MCP client, manager, OAuth, and runtime tests.",
    "integration_http_client": "Run HTTP client integration tests.",
}

CHECK_FIX_HINTS: Mapping[str, str] = {
    "thesis_output_language_zh": "Re-check thesis service/handler payload output_language='zh' enforcement and rerun workspace matrix tests.",
    "sci_output_language_en": "Re-check sci service/handler payload output_language='en' enforcement and rerun workspace matrix tests.",
    "workspace_e2e_matrix": "Run `PYTHONPATH=. uv run pytest tests/workspace_features/test_workspace_e2e_matrix.py -q` and fix failing workspace behavior.",
    "feature_submission_service_regression": "Run `PYTHONPATH=. uv run pytest tests/application/services/test_feature_submission_service.py -q` and fix task lifecycle regressions.",
    "executor_dual_mode": "Run `PYTHONPATH=. uv run pytest tests/task/test_executor.py tests/task/test_service_executor.py -q` and fix executor regressions.",
    "observability_sentry": "Run `PYTHONPATH=. uv run pytest tests/observability/test_sentry.py -q` and fix Sentry setup regressions.",
    "observability_prometheus": "Run `PYTHONPATH=. uv run pytest tests/observability/test_prometheus.py -q` and fix metrics regressions.",
    "agent_status_tracking": "Run `PYTHONPATH=. uv run pytest tests/task/test_agent_status.py -q` and fix task/agent status regressions.",
    "workspace_lock": "Run `PYTHONPATH=. uv run pytest tests/application/services/test_feature_submission_workspace_lock.py -q` and fix workspace locking regressions.",
    "task_metrics": "Run `PYTHONPATH=. uv run pytest tests/task/test_task_metrics.py -q` and fix task metrics regressions.",
    "semantic_scholar_reference_search": "Run `PYTHONPATH=. uv run pytest tests/academic/literature/test_search_service.py -q` and fix Semantic Scholar retrieval regressions.",
    "reference_upload_preprocess": "Run `PYTHONPATH=. uv run pytest tests/gateway/routers/test_uploads.py tests/task/test_document_preprocess_handler.py -q` and `cd frontend && npm test -- thread-store-support.test.ts`; fix upload/preprocess visibility and refresh regressions.",
    "artifact_refresh_workflow": "Run `PYTHONPATH=. uv run pytest tests/task/test_store.py::TestTaskStorePostgres::test_mark_task_completed_publishes_canonical_task_activity -q` and fix artifact refresh regressions.",
    "artifact_followup_workflow": "Run `PYTHONPATH=. uv run pytest tests/services/test_workspace_activity_service.py::test_task_activity_promotes_result_artifact_as_retry_seed -q` and fix artifact follow-up route seed regressions.",
    "reference_writing_workflow": "Run `PYTHONPATH=. uv run pytest tests/services/test_reference_writing_workflow_gate.py -q` and fix Reference Library writing workflow regressions.",
    "prism_review_workflow": "Run `PYTHONPATH=. uv run pytest tests/services/test_prism_review_workflow_gate.py tests/compute/test_projection_service.py -q` and fix Prism review workflow regressions.",
    "sci_reference_search": "Run `PYTHONPATH=. uv run pytest tests/workspace_features/services/test_sci_feature_service.py -q` and fix SCI reference search regressions.",
    "auth_email_workflow": "Run `PYTHONPATH=. uv run pytest tests/services/test_auth_email_workflow_gate.py tests/gateway/routers/test_auth.py tests/services/test_email_service.py -q` and fix login/register verification regressions.",
    "frontend_typescript_check": "Run `cd frontend && npx tsc --noEmit` and resolve TypeScript errors.",
    "integration_tool_chain": "Run `PYTHONPATH=. uv run pytest tests/integration/test_tool_chain.py -q` and fix external chain regressions.",
    "mcp_runtime": "Run `PYTHONPATH=. uv run pytest tests/mcp -q` and fix MCP runtime regressions.",
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
