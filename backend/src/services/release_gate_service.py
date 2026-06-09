"""Service to execute release gate checks and build launch readiness reports."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.quality.release_gate import evaluate_release_gate


@dataclass(frozen=True)
class ReleaseGateCommand:
    """A single executable check command for release gate."""

    check_id: str
    command: tuple[str, ...]
    cwd: Path


class ReleaseGateService:
    """Run core/extended checks and return a release gate report."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        backend_root: Path | None = None,
        timeout_seconds: int = 600,
    ):
        resolved_backend_root = backend_root or Path(__file__).resolve().parents[2]
        self.backend_root = resolved_backend_root
        self.project_root = project_root or resolved_backend_root.parent
        self.timeout_seconds = timeout_seconds
        self.uv_binary = self._resolve_uv_binary()

    def _uv_command(self, *args: str) -> tuple[str, ...]:
        return (self.uv_binary, *args)

    @staticmethod
    def _resolve_uv_binary() -> str:
        configured = os.environ.get("UV_BINARY")
        if configured:
            return configured
        from_path = shutil.which("uv")
        if from_path:
            return from_path
        local_uv = Path.home() / ".local" / "bin" / "uv"
        if local_uv.exists():
            return str(local_uv)
        return "uv"

    @property
    def core_commands(self) -> tuple[ReleaseGateCommand, ...]:
        return (
            ReleaseGateCommand(
                check_id="executor_dual_mode",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/task/test_executor.py",
                    "tests/task/test_service_executor.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="observability_sentry",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/observability/test_sentry.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="observability_prometheus",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/observability/test_prometheus.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="agent_status_tracking",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/task/test_agent_status.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="task_metrics",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/task/test_task_metrics.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="semantic_scholar_reference_search",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/academic/literature/test_search_service.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="reference_upload_preprocess",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/gateway/routers/test_uploads.py",
                    "tests/task/test_document_preprocess_handler.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="artifact_refresh_workflow",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/task/test_store.py::TestTaskStorePostgres::test_mark_task_completed_publishes_canonical_task_activity",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="artifact_followup_workflow",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/services/test_workspace_activity_service.py::test_task_activity_promotes_result_artifact_as_retry_seed",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="reference_writing_workflow",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/services/test_reference_writing_workflow_gate.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="prism_review_workflow",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/services/test_prism_review_workflow_gate.py",
                    "tests/compute/test_projection_service.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="auth_email_workflow",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/services/test_auth_email_workflow_gate.py",
                    "tests/gateway/routers/test_auth.py",
                    "tests/services/test_email_service.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="execution_commit_writeback_security",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/gateway/routers/test_execution_commit_router.py",
                    "tests/services/test_execution_commit_service.py::test_commit_rejects_non_owner_before_room_writes",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="execution_resume_runtime_config",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/application/handlers/test_thread_turn_runtime_config.py",
                    "tests/application/handlers/test_thread_turn_handler.py::TestThreadTurnHandlerCancellation::test_generate_thread_response_passes_execution_id_to_runtime",
                    "tests/application/handlers/test_thread_turn_handler.py::TestThreadTurnHandlerCancellation::test_stream_thread_response_passes_execution_id_to_runtime",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="execution_ux_convergence",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/application/handlers/test_thread_turn_handler.py",
                    "tests/gateway/routers/test_workspace_rooms_router.py::TestRunsRoom::test_list_runs_happy",
                    "tests/integration/test_chat_to_feature_launch.py",
                    "tests/tools/test_launch_feature_tool.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="native_harness_quality_gate",
                command=self._uv_command(
                    "run",
                    "pytest",
                    "tests/agents/harness/test_scheduler_and_python_tool.py",
                    "tests/agents/harness/test_sandbox_file_tools.py",
                    "tests/agents/harness/test_command_audit.py",
                    "tests/agents/harness/test_policy_and_registry.py",
                    "tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py",
                    "tests/agents/harness/test_research_task_eval.py",
                    "tests/agents/harness/test_langchain_adapter.py",
                    "tests/agents/harness/test_context_assembly.py",
                    "tests/agents/lead_agent/v2/test_workspace_sandbox_manager.py",
                    "tests/architecture/test_native_harness_boundaries.py",
                    "tests/dataservice/test_sandbox_domain.py",
                    "tests/sandbox/test_workspace_layout.py",
                    "tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py",
                    "tests/agents/lead_agent/v2/test_citation_source_audit.py",
                    "tests/agents/lead_agent/v2/test_team_quality_gates.py",
                    "tests/integration/test_harness_mock_sandbox_e2e.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="model_catalog_pricing_gate",
                command=self._uv_command(
                    "run",
                    "python",
                    "-m",
                    "src.quality.model_catalog_pricing_gate",
                    "--json",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="frontend_typescript_check",
                command=("npm", "run", "typecheck"),
                cwd=self.project_root / "frontend",
            ),
            ReleaseGateCommand(
                check_id="frontend_lint",
                command=("npm", "run", "lint"),
                cwd=self.project_root / "frontend",
            ),
            ReleaseGateCommand(
                check_id="frontend_execution_ux_unit_tests",
                command=(
                    "npx",
                    "vitest",
                    "run",
                    "tests/unit/lib/execution-run-view.test.ts",
                    "tests/unit/stores/chat-store.test.ts",
                    "tests/unit/hooks/useWorkspaceEventStream.test.tsx",
                    "tests/unit/v2/rooms/RunsDrawer.test.tsx",
                    "tests/unit/v2/ExecutionCard.test.tsx",
                    "tests/unit/v2/ChatPanel.test.tsx",
                ),
                cwd=self.project_root / "frontend",
            ),
            ReleaseGateCommand(
                check_id="frontend_static_build",
                command=("npm", "run", "build"),
                cwd=self.project_root / "frontend",
            ),
        )

    @property
    def extended_commands(self) -> tuple[ReleaseGateCommand, ...]:
        return (
            ReleaseGateCommand(
                check_id="integration_tool_chain",
                command=self._uv_command("run", "pytest", "tests/integration/test_tool_chain.py", "-q"),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="mcp_runtime",
                command=self._uv_command("run", "pytest", "tests/mcp", "-q"),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="integration_http_client",
                command=self._uv_command("run", "pytest", "tests/integration/test_http_client.py", "-q"),
                cwd=self.backend_root,
            ),
        )

    async def run(self, *, include_extended: bool = False) -> dict[str, Any]:
        """Execute release checks and evaluate gate status."""

        core_results, core_details = await asyncio.to_thread(
            self._execute_checks,
            self.core_commands,
        )

        extended_results: dict[str, bool] | None = None
        extended_details: dict[str, dict[str, Any]] = {}
        if include_extended:
            extended_results, extended_details = await asyncio.to_thread(
                self._execute_checks,
                self.extended_commands,
            )

        report = evaluate_release_gate(
            core_results=core_results,
            extended_results=extended_results,
        )
        self._attach_runtime_details(report, core_details, extended_details)
        report["include_extended"] = include_extended
        report["runner"] = {
            "project_root": str(self.project_root),
            "backend_root": str(self.backend_root),
            "timeout_seconds": self.timeout_seconds,
            "uv_binary": self.uv_binary,
        }
        return report

    def _execute_checks(
        self,
        checks: tuple[ReleaseGateCommand, ...],
    ) -> tuple[dict[str, bool], dict[str, dict[str, Any]]]:
        results: dict[str, bool] = {}
        details: dict[str, dict[str, Any]] = {}

        for check in checks:
            started_at = time.perf_counter()
            return_code = -1
            output_tail = ""
            error: str | None = None

            try:
                completed = subprocess.run(
                    list(check.command),
                    cwd=str(check.cwd),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                return_code = completed.returncode
                output = self._join_process_output(completed.stdout, completed.stderr)
                output_tail = self._tail_output(output)
                success = completed.returncode == 0
            except subprocess.TimeoutExpired as exc:
                output = self._join_process_output(exc.stdout, exc.stderr)
                output_tail = self._tail_output(output)
                error = f"timeout after {self.timeout_seconds}s"
                success = False
            except FileNotFoundError as exc:
                error = str(exc)
                success = False
            except Exception as exc:  # pragma: no cover - defensive
                error = str(exc)
                success = False

            duration_seconds = round(time.perf_counter() - started_at, 3)
            results[check.check_id] = success
            details[check.check_id] = {
                "command": " ".join(check.command),
                "cwd": str(check.cwd),
                "return_code": return_code,
                "duration_seconds": duration_seconds,
                "output_tail": output_tail,
                "error": error,
            }

        return results, details

    @staticmethod
    def _normalize_process_output(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    @classmethod
    def _join_process_output(cls, stdout: str | bytes | None, stderr: str | bytes | None) -> str:
        return "\n".join(
            part
            for part in [
                cls._normalize_process_output(stdout),
                cls._normalize_process_output(stderr),
            ]
            if part
        ).strip()

    @staticmethod
    def _tail_output(output: str, limit: int = 40) -> str:
        if not output:
            return ""
        lines = output.splitlines()
        if len(lines) <= limit:
            return "\n".join(lines)
        return "\n".join(lines[-limit:])

    @staticmethod
    def _attach_runtime_details(
        report: dict[str, Any],
        core_details: dict[str, dict[str, Any]],
        extended_details: dict[str, dict[str, Any]],
    ) -> None:
        for check in report.get("core_gate", {}).get("checks", []):
            detail = core_details.get(check["id"])
            if detail:
                check["runtime"] = detail
        for check in report.get("extended_gate", {}).get("checks", []):
            detail = extended_details.get(check["id"])
            if detail:
                check["runtime"] = detail
