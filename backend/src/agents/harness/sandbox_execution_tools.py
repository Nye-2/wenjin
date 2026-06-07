"""Execution tools backed by the existing Lead Agent sandbox runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

        payload = await self.scheduler.run(
            self.context.workspace_id,
            _run,
            timeout_seconds=min(self.policy.max_sandbox_seconds, 30),
        )
        await self._publish_command_audit_events(payload)
        status = str(payload.get("status") or "completed")
        preview = f"Python execution {status}"
        parsed = payload.get("parsed_stdout")
        if parsed:
            preview = f"{preview}: {str(parsed)[:500]}"
        elif payload.get("stdout"):
            preview = f"{preview}: {str(payload['stdout'])[:500]}"
        output_refs = tuple(str(ref) for ref in payload.get("output_refs") or () if str(ref).strip())
        externalized = bool(output_refs or payload.get("stdout_externalized") or payload.get("stderr_externalized"))
        return HarnessToolResult(
            preview_text=preview,
            structured_payload=dict(payload),
            output_refs=output_refs,
            truncated=externalized,
            externalized=externalized,
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
