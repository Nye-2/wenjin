"""Execute strict Mission release-gate commands."""

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
    check_id: str
    command: tuple[str, ...]
    cwd: Path


class ReleaseGateService:
    def __init__(
        self,
        *,
        project_root: Path | None = None,
        backend_root: Path | None = None,
        timeout_seconds: int = 600,
    ) -> None:
        self.backend_root = backend_root or Path(__file__).resolve().parents[2]
        self.project_root = project_root or self.backend_root.parent
        self.timeout_seconds = timeout_seconds
        self.uv_binary = self._resolve_uv_binary()

    def _uv_command(self, *args: str) -> tuple[str, ...]:
        return (self.uv_binary, *args)

    @staticmethod
    def _resolve_uv_binary() -> str:
        if configured := os.environ.get("UV_BINARY"):
            return configured
        if from_path := shutil.which("uv"):
            return from_path
        local = Path.home() / ".local" / "bin" / "uv"
        return str(local) if local.exists() else "uv"

    def _pytest(self, *paths: str) -> tuple[str, ...]:
        return self._uv_command("run", "pytest", *paths, "-q")

    @property
    def core_commands(self) -> tuple[ReleaseGateCommand, ...]:
        backend = self.backend_root
        frontend = self.project_root / "frontend"
        return (
            ReleaseGateCommand(
                "mission_store",
                self._pytest(
                    "tests/dataservice/test_mission_store.py",
                    "tests/dataservice/test_mission_router.py",
                    "tests/dataservice_client/test_mission_client.py",
                    "tests/database/test_mission_models.py",
                ),
                backend,
            ),
            ReleaseGateCommand(
                "mission_runtime",
                self._pytest(
                    "tests/mission_runtime",
                    "tests/task/test_mission_task.py",
                ),
                backend,
            ),
            ReleaseGateCommand(
                "mission_catalog",
                self._uv_command(
                    "run",
                    "python",
                    "-m",
                    "src.quality.mission_catalog_gate",
                ),
                backend,
            ),
            ReleaseGateCommand(
                "workspace_agent",
                self._pytest(
                    "tests/agents/workspace_agent",
                    "tests/application/handlers/test_workspace_agent_turn.py",
                    "tests/gateway/routers/test_missions_contract.py",
                ),
                backend,
            ),
            ReleaseGateCommand(
                "subagent_runtime",
                self._pytest(
                    "tests/subagent_runtime",
                    "tests/mission_runtime/test_subagent_composition.py",
                ),
                backend,
            ),
            ReleaseGateCommand(
                "tool_orchestrator",
                self._pytest(
                    "tests/tools/test_tool_orchestrator.py",
                ),
                backend,
            ),
            ReleaseGateCommand(
                "model_capability",
                self._pytest(
                    "tests/models/test_capability_probe.py",
                    "tests/services/test_model_catalog_cache.py",
                    "tests/services/search/test_model_native_search.py",
                ),
                backend,
            ),
            ReleaseGateCommand(
                "sandbox_security",
                self._pytest(
                    "tests/sandbox",
                    "tests/agents/harness/test_sandbox_execution_tools.py",
                ),
                backend,
            ),
            ReleaseGateCommand(
                "review_commit",
                self._pytest(
                    "tests/review_commit_runtime",
                    "tests/permission_runtime",
                ),
                backend,
            ),
            ReleaseGateCommand(
                "mission_cutover",
                self._uv_command(
                    "run",
                    "python",
                    "-m",
                    "src.quality.mission_cutover_gate",
                    "--project-root",
                    str(self.project_root),
                ),
                backend,
            ),
            ReleaseGateCommand(
                "frontend_mission",
                (
                    "npx",
                    "vitest",
                    "run",
                    "tests/unit/lib/mission-view.test.ts",
                    "tests/unit/stores/mission-ui-store.test.ts",
                    "tests/unit/v2/MissionConsole.test.tsx",
                ),
                frontend,
            ),
            ReleaseGateCommand(
                "frontend_typecheck",
                ("npm", "run", "typecheck"),
                frontend,
            ),
        )

    @property
    def extended_commands(self) -> tuple[ReleaseGateCommand, ...]:
        return (
            ReleaseGateCommand(
                "backend_full_suite",
                self._pytest("tests"),
                self.backend_root,
            ),
            ReleaseGateCommand(
                "frontend_build",
                ("npm", "run", "build"),
                self.project_root / "frontend",
            ),
            ReleaseGateCommand(
                "mission_browser_e2e",
                (
                    "npx",
                    "playwright",
                    "test",
                    "tests/e2e/mission-console-main-chain.spec.ts",
                ),
                self.project_root / "frontend",
            ),
        )

    async def run(self, *, include_extended: bool = False) -> dict[str, Any]:
        core_results, core_details = await asyncio.to_thread(self._execute_checks, self.core_commands)
        extended_results: dict[str, bool] | None = None
        extended_details: dict[str, dict[str, Any]] = {}
        if include_extended:
            extended_results, extended_details = await asyncio.to_thread(self._execute_checks, self.extended_commands)
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
            started = time.perf_counter()
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
                output_tail = self._tail_output(self._join_process_output(completed.stdout, completed.stderr))
                success = return_code == 0
            except subprocess.TimeoutExpired as exc:
                output_tail = self._tail_output(self._join_process_output(exc.stdout, exc.stderr))
                error = f"timeout after {self.timeout_seconds}s"
                success = False
            except (FileNotFoundError, OSError) as exc:
                error = str(exc)
                success = False
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            results[check.check_id] = success
            details[check.check_id] = {
                "command": list(check.command),
                "cwd": str(check.cwd),
                "return_code": return_code,
                "duration_ms": elapsed_ms,
                "output_tail": output_tail,
                "error": error,
            }
        return results, details

    @staticmethod
    def _join_process_output(stdout: Any, stderr: Any) -> str:
        def decode(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return str(value)

        return "\n".join(part for part in (decode(stdout).strip(), decode(stderr).strip()) if part)

    @staticmethod
    def _tail_output(output: str, *, line_limit: int = 80) -> str:
        return "\n".join(output.splitlines()[-line_limit:])

    @staticmethod
    def _attach_runtime_details(
        report: dict[str, Any],
        core_details: dict[str, dict[str, Any]],
        extended_details: dict[str, dict[str, Any]],
    ) -> None:
        for item in report["core_gate"]["checks"]:
            item["runtime"] = core_details.get(item["id"])
        for item in report["extended_gate"]["checks"]:
            item["runtime"] = extended_details.get(item["id"])
