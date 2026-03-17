"""Service to execute release gate checks and build launch readiness reports."""

from __future__ import annotations

import asyncio
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

    @property
    def core_commands(self) -> tuple[ReleaseGateCommand, ...]:
        return (
            ReleaseGateCommand(
                check_id="thesis_output_language_zh",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/workspace_features/test_workspace_e2e_matrix.py::test_thesis_output_language_is_forced_to_zh_for_any_template",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="sci_output_language_en",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/workspace_features/test_workspace_e2e_matrix.py::test_sci_output_language_constant_is_en",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="workspace_e2e_matrix",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/workspace_features/test_workspace_e2e_matrix.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="features_router_regression",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/gateway/routers/test_features.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="feature_execution_handler_regression",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/application/handlers/test_feature_execution_handler.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="five_workspace_smoke",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/workspace_features/test_five_workspace_smoke.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="executor_dual_mode",
                command=(
                    "uv",
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
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/observability/test_sentry.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="observability_prometheus",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/observability/test_prometheus.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="agent_status_tracking",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/task/test_agent_status.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="workspace_lock",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/application/handlers/test_workspace_lock.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="task_metrics",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/task/test_task_metrics.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="extraction_tier2",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/academic/services/test_extraction_tier2.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="fuzzy_section_matching",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/academic/literature/test_fuzzy_matching.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="workspace_search",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/academic/literature/test_search_workspace.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="enriched_toc",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/academic/literature/test_enriched_toc.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="section_redis_cache",
                command=(
                    "uv",
                    "run",
                    "pytest",
                    "tests/academic/literature/test_redis_cache.py",
                    "-q",
                ),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="frontend_typescript_check",
                command=("npx", "tsc", "--noEmit"),
                cwd=self.project_root / "frontend",
            ),
        )

    @property
    def extended_commands(self) -> tuple[ReleaseGateCommand, ...]:
        return (
            ReleaseGateCommand(
                check_id="integration_tool_chain",
                command=("uv", "run", "pytest", "tests/integration/test_tool_chain.py", "-q"),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="mcp_academic_tools",
                command=("uv", "run", "pytest", "tests/mcp/test_academic_tools.py", "-q"),
                cwd=self.backend_root,
            ),
            ReleaseGateCommand(
                check_id="integration_http_client",
                command=("uv", "run", "pytest", "tests/integration/test_http_client.py", "-q"),
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
                output = "\n".join(
                    part for part in [completed.stdout, completed.stderr] if part
                ).strip()
                output_tail = self._tail_output(output)
                success = completed.returncode == 0
            except subprocess.TimeoutExpired as exc:
                output = "\n".join(
                    part
                    for part in [
                        str(exc.stdout or ""),
                        str(exc.stderr or ""),
                    ]
                    if part
                ).strip()
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
