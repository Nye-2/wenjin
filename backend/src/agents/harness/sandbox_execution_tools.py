"""Execution tools backed by the existing Lead Agent sandbox runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agents.lead_agent.v2.sandbox_errors import SandboxCommandExecutionError
from src.agents.lead_agent.v2.sandbox_job_runner import SandboxJobRunner
from src.agents.lead_agent.v2.sandbox_script_executor import sanitize_script_name

from .contracts import HarnessPolicy, HarnessRunContext, HarnessToolResult
from .events import publish_harness_event
from .scheduler import WorkspaceToolScheduler, default_workspace_tool_scheduler


@dataclass(slots=True)
class SandboxExecutionTools:
    """Python execution wrapper for harness tools."""

    context: HarnessRunContext
    policy: HarnessPolicy
    runner: Any | None = None
    scheduler: WorkspaceToolScheduler = default_workspace_tool_scheduler

    async def run_python(
        self,
        *,
        script: str,
        script_name: str = "analysis.py",
        dependency_hints: list[str] | str | None = None,
        billing_reservation_id: str | None = None,
    ) -> HarnessToolResult:
        if "sandbox.run_python" not in self.policy.permissions:
            raise PermissionError("harness policy does not allow sandbox.run_python")

        safe_script_name = sanitize_script_name(script_name)
        runner = self.runner or SandboxJobRunner()

        async def _run() -> dict[str, Any]:
            return await runner.run_python_script(
                workspace_id=self.context.workspace_id,
                execution_id=self.context.execution_id,
                node_id=self.context.node_id,
                sandbox_policy=self._sandbox_policy(),
                script=script,
                script_name=safe_script_name,
                dependency_hints=dependency_hints,
                billing_reservation_id=billing_reservation_id,
            )

        timeout_seconds = min(self.policy.max_sandbox_seconds, 30)
        try:
            payload = await self.scheduler.run(
                self.context.workspace_id,
                _run,
                timeout_seconds=timeout_seconds,
            )
        except SandboxCommandExecutionError as exc:
            payload = dict(exc.output)
            payload.setdefault("status", "failed")
            payload["failure_classification"] = _classify_run_python_failure(payload)
            payload["error_code"] = payload["failure_classification"]["failure_code"]
        payload["execution_manifest"] = _execution_manifest(
            context=self.context,
            sandbox_policy=self._sandbox_policy(),
            script_name=safe_script_name,
            dependency_hints=dependency_hints,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        await self._publish_command_audit_events(payload)
        status = str(payload.get("status") or "completed")
        failure_classification = payload.get("failure_classification")
        error = _failure_error(failure_classification)
        preview = f"Python execution {status}"
        if error:
            preview = f"{preview}: {error}"
        parsed = payload.get("parsed_stdout")
        if parsed:
            preview = f"{preview}: {str(parsed)[:500]}"
        elif payload.get("stdout") and not error:
            preview = f"{preview}: {str(payload['stdout'])[:500]}"
        output_refs = tuple(str(ref) for ref in payload.get("output_refs") or () if str(ref).strip())
        externalized = bool(output_refs or payload.get("stdout_externalized") or payload.get("stderr_externalized"))
        return HarnessToolResult(
            preview_text=preview,
            structured_payload=dict(payload),
            output_refs=output_refs,
            truncated=externalized,
            externalized=externalized,
            error=error,
        )

    async def _publish_command_audit_events(self, payload: dict[str, Any]) -> None:
        sandbox_job_id = str(payload.get("sandbox_job_id") or "").strip()
        command_audit = payload.get("command_audit")
        if isinstance(command_audit, dict):
            await publish_harness_event(
                self.context,
                "command_audit",
                visibility="team_visible",
                sequence_kind="audit",
                payload={
                    "name": "sandbox.run_python",
                    "sandbox_job_id": sandbox_job_id,
                    "command_audit": dict(command_audit),
                },
            )
        install_job_ids = [str(item) for item in payload.get("install_job_ids") or [] if str(item).strip()]
        install_audits = payload.get("install_command_audits")
        if not isinstance(install_audits, list):
            return
        for index, raw_audit in enumerate(install_audits):
            if not isinstance(raw_audit, dict):
                continue
            await publish_harness_event(
                self.context,
                "command_audit",
                visibility="team_visible",
                sequence_kind="audit",
                payload={
                    "name": "sandbox.install_dependencies",
                    "sandbox_job_id": install_job_ids[index] if index < len(install_job_ids) else "",
                    "run_sandbox_job_id": sandbox_job_id,
                    "command_audit": dict(raw_audit),
                },
            )

    def _sandbox_policy(self) -> dict[str, Any]:
        raw = self.context.capability_policy.get("sandbox_policy")
        policy = dict(raw) if isinstance(raw, dict) else {}
        if self.policy.allow_package_install:
            policy["allow_package_install"] = True
        policy.setdefault("allowed_operations", ["run_python"])
        return policy


def _execution_manifest(
    *,
    context: HarnessRunContext,
    sandbox_policy: dict[str, Any],
    script_name: str,
    dependency_hints: list[str] | str | None,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    return {
        "schema": "wenjin.harness.run_python.execution_manifest.v1",
        "tool": "sandbox.run_python",
        "workspace_id": context.workspace_id,
        "execution_id": context.execution_id,
        "node_id": context.node_id,
        "invocation_id": context.invocation_id,
        "script_name": str(payload.get("script_name") or script_name),
        "script_path": str(payload.get("script_path") or f"/workspace/scripts/{script_name}"),
        "dependency_hints": _dependency_hints(payload.get("dependency_hints", dependency_hints)),
        "sandbox_job_id": str(payload.get("sandbox_job_id") or ""),
        "sandbox_environment_id": str(payload.get("sandbox_environment_id") or ""),
        "network_profile": str(sandbox_policy.get("network_profile") or "none"),
        "timeout_seconds": timeout_seconds,
    }


def _classify_run_python_failure(payload: dict[str, Any]) -> dict[str, Any]:
    exit_code = _int_or_none(payload.get("exit_code"))
    stderr = str(payload.get("stderr") or "").strip()
    if exit_code is not None and exit_code != 0:
        return {
            "schema": "wenjin.harness.run_python.failure_classification.v1",
            "category": "user_code",
            "reason": "nonzero_exit",
            "failure_code": "python_exit_nonzero",
            "exit_code": exit_code,
            "stderr_preview": _compact_text(stderr),
            "recoverable": True,
        }
    return {
        "schema": "wenjin.harness.run_python.failure_classification.v1",
        "category": "sandbox_runtime",
        "reason": "runner_exception",
        "failure_code": "sandbox_job_failed",
        "exit_code": exit_code,
        "stderr_preview": _compact_text(stderr),
        "recoverable": False,
    }


def _failure_error(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    failure_code = str(raw.get("failure_code") or "sandbox_job_failed").strip()
    exit_code = raw.get("exit_code")
    if isinstance(exit_code, int):
        return f"{failure_code}: exit_code={exit_code}"
    return failure_code


def _dependency_hints(raw: Any) -> list[str]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list | tuple | set):
        values = list(raw)
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip()]


def _compact_text(text: str) -> str:
    value = str(text or "").strip()
    return value if len(value) <= 500 else f"{value[:497]}..."


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
