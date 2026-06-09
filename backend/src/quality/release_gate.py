"""Release gate evaluator for five-workspace production launch."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

CORE_GATE_CHECKS: tuple[str, ...] = (
    "executor_dual_mode",
    "observability_sentry",
    "observability_prometheus",
    "agent_status_tracking",
    "task_metrics",
    "semantic_scholar_reference_search",
    "reference_upload_preprocess",
    "artifact_refresh_workflow",
    "artifact_followup_workflow",
    "reference_writing_workflow",
    "prism_review_workflow",
    "auth_email_workflow",
    "execution_commit_writeback_security",
    "execution_resume_runtime_config",
    "execution_ux_convergence",
    "native_harness_quality_gate",
    "model_catalog_pricing_gate",
    "frontend_typescript_check",
    "frontend_lint",
    "frontend_execution_ux_unit_tests",
    "frontend_static_build",
)

EXTENDED_GATE_CHECKS: tuple[str, ...] = (
    "integration_tool_chain",
    "mcp_runtime",
    "integration_http_client",
)

CHECK_DESCRIPTIONS: Mapping[str, str] = {
    "executor_dual_mode": "Run dual-mode executor tests (Celery + local asyncio).",
    "observability_sentry": "Run Sentry observability configuration tests.",
    "observability_prometheus": "Run Prometheus metrics observability tests.",
    "agent_status_tracking": "Run agent status tracking tests.",
    "task_metrics": "Run task metrics tests.",
    "semantic_scholar_reference_search": "Run Semantic Scholar reference search tests.",
    "reference_upload_preprocess": "Run reference upload and document preprocess tests.",
    "artifact_refresh_workflow": "Run artifact persistence, workspace refresh, and frontend artifact reload contract tests.",
    "artifact_followup_workflow": "Run artifact open, follow-up, and rerun seed workflow gate tests.",
    "reference_writing_workflow": "Run Reference Library evidence, usage, BibTeX, and Prism workflow gate tests.",
    "prism_review_workflow": "Run Prism pending-review, file-change, and compute projection workflow gate tests.",
    "auth_email_workflow": "Run auth registration, email verification code, and frontend auth flow contract tests.",
    "execution_commit_writeback_security": "Run execution result-card writeback authentication and ownership tests.",
    "execution_resume_runtime_config": "Run execution resume runtime-config propagation tests.",
    "execution_ux_convergence": "Run chat-to-execution and RunView convergence tests.",
    "native_harness_quality_gate": "Run Wenjin-native harness filesystem, policy, command audit, output budget, context, architecture boundary, DataService sandbox, citation/source audit, and mock sandbox E2E tests.",
    "model_catalog_pricing_gate": "Run model catalog, secret, and pricing readiness checks.",
    "frontend_typescript_check": "Run frontend TypeScript compile check.",
    "frontend_lint": "Run frontend lint check.",
    "frontend_execution_ux_unit_tests": "Run frontend execution UX projection, stream, and runs tests.",
    "frontend_static_build": "Run frontend production build.",
    "integration_tool_chain": "Run integration test for tool chain.",
    "mcp_runtime": "Run MCP client, manager, OAuth, and runtime tests.",
    "integration_http_client": "Run HTTP client integration tests.",
}

CHECK_FIX_HINTS: Mapping[str, str] = {
    "executor_dual_mode": "Run `PYTHONPATH=. uv run pytest tests/task/test_executor.py tests/task/test_service_executor.py -q` and fix executor regressions.",
    "observability_sentry": "Run `PYTHONPATH=. uv run pytest tests/observability/test_sentry.py -q` and fix Sentry setup regressions.",
    "observability_prometheus": "Run `PYTHONPATH=. uv run pytest tests/observability/test_prometheus.py -q` and fix metrics regressions.",
    "agent_status_tracking": "Run `PYTHONPATH=. uv run pytest tests/task/test_agent_status.py -q` and fix task/agent status regressions.",
    "task_metrics": "Run `PYTHONPATH=. uv run pytest tests/task/test_task_metrics.py -q` and fix task metrics regressions.",
    "semantic_scholar_reference_search": "Run `PYTHONPATH=. uv run pytest tests/academic/literature/test_search_service.py -q` and fix Semantic Scholar retrieval regressions.",
    "reference_upload_preprocess": "Run `PYTHONPATH=. uv run pytest tests/gateway/routers/test_uploads.py tests/task/test_document_preprocess_handler.py -q` and `cd frontend && npm test -- thread-store-support.test.ts`; fix upload/preprocess visibility and refresh regressions.",
    "artifact_refresh_workflow": "Run `PYTHONPATH=. uv run pytest tests/task/test_store.py::TestTaskStorePostgres::test_mark_task_completed_publishes_canonical_task_activity -q` and fix artifact refresh regressions.",
    "artifact_followup_workflow": "Run `PYTHONPATH=. uv run pytest tests/services/test_workspace_activity_service.py::test_task_activity_promotes_result_artifact_as_retry_seed -q` and fix artifact follow-up route seed regressions.",
    "reference_writing_workflow": "Run `PYTHONPATH=. uv run pytest tests/services/test_reference_writing_workflow_gate.py -q` and fix Reference Library writing workflow regressions.",
    "prism_review_workflow": "Run `PYTHONPATH=. uv run pytest tests/services/test_prism_review_workflow_gate.py tests/compute/test_projection_service.py -q` and fix Prism review workflow regressions.",
    "auth_email_workflow": "Run `PYTHONPATH=. uv run pytest tests/services/test_auth_email_workflow_gate.py tests/gateway/routers/test_auth.py tests/services/test_email_service.py -q` and fix login/register verification regressions.",
    "execution_commit_writeback_security": "Run `PYTHONPATH=. uv run pytest tests/gateway/routers/test_execution_commit_router.py tests/services/test_execution_commit_service.py::test_commit_rejects_non_owner_before_room_writes -q` and fix execution commit ownership regressions.",
    "execution_resume_runtime_config": "Run `PYTHONPATH=. uv run pytest tests/application/handlers/test_thread_turn_runtime_config.py tests/application/handlers/test_thread_turn_handler.py::TestThreadTurnHandlerCancellation::test_generate_thread_response_passes_execution_id_to_runtime tests/application/handlers/test_thread_turn_handler.py::TestThreadTurnHandlerCancellation::test_stream_thread_response_passes_execution_id_to_runtime -q` and fix resume execution_id propagation.",
    "execution_ux_convergence": "Run `PYTHONPATH=. uv run pytest tests/application/handlers/test_thread_turn_handler.py tests/gateway/routers/test_workspace_rooms_router.py::TestRunsRoom::test_list_runs_happy tests/integration/test_chat_to_feature_launch.py tests/tools/test_launch_feature_tool.py -q` and fix execution UX convergence regressions.",
    "native_harness_quality_gate": "Run `PYTHONPATH=. uv run pytest tests/agents/harness/test_scheduler_and_python_tool.py tests/agents/harness/test_sandbox_file_tools.py tests/agents/harness/test_command_audit.py tests/agents/harness/test_policy_and_registry.py tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py tests/agents/harness/test_langchain_adapter.py tests/agents/harness/test_context_assembly.py tests/agents/lead_agent/v2/test_workspace_sandbox_manager.py tests/architecture/test_native_harness_boundaries.py tests/dataservice/test_sandbox_domain.py tests/sandbox/test_workspace_layout.py tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py tests/agents/lead_agent/v2/test_citation_source_audit.py tests/agents/lead_agent/v2/test_team_quality_gates.py tests/integration/test_harness_mock_sandbox_e2e.py -q` and fix native harness regressions.",
    "model_catalog_pricing_gate": "Run `PYTHONPATH=. uv run python -m src.quality.model_catalog_pricing_gate --json` and configure model catalog/pricing readiness failures.",
    "frontend_typescript_check": "Run `cd frontend && npm run typecheck` and resolve TypeScript errors.",
    "frontend_lint": "Run `cd frontend && npm run lint` and resolve lint errors.",
    "frontend_execution_ux_unit_tests": "Run `cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts tests/unit/stores/chat-store.test.ts tests/unit/hooks/useWorkspaceEventStream.test.tsx tests/unit/v2/rooms/RunsDrawer.test.tsx tests/unit/v2/ExecutionCard.test.tsx tests/unit/v2/ChatPanel.test.tsx` and fix execution UX regressions.",
    "frontend_static_build": "Run `cd frontend && npm run build` and resolve production build errors.",
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
