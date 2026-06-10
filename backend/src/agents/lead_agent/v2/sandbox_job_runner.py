"""Job orchestration for lead-agent sandbox runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.agents.harness.command_audit import (
    CommandAuditPolicy,
    HarnessCommand,
    audit_command,
    require_command_policy_allowed,
)
from src.agents.lead_agent.v2.sandbox_artifact_collector import SandboxArtifactCollector
from src.agents.lead_agent.v2.sandbox_artifact_discovery import discover_generated_artifacts
from src.agents.lead_agent.v2.sandbox_dataset_manifest import sync_dataset_manifest
from src.agents.lead_agent.v2.sandbox_environment_installer import SandboxEnvironmentInstaller
from src.agents.lead_agent.v2.sandbox_errors import SandboxCommandExecutionError
from src.agents.lead_agent.v2.sandbox_execution_lifecycle import (
    build_sandbox_execution_lifecycle,
    finalize_sandbox_execution_lifecycle,
)
from src.agents.lead_agent.v2.sandbox_runtime_session import (
    SandboxRuntimeSession,
    exception_exit_code_for_job,
    mark_job_failed,
    provider_image,
)
from src.agents.lead_agent.v2.sandbox_script_executor import (
    SandboxScriptExecutor,
    sandbox_script_execution_env,
)
from src.agents.lead_agent.v2.sandbox_stream_budgeting import budget_script_streams
from src.agents.lead_agent.v2.workspace_sandbox import WorkspaceSandboxManager
from src.sandbox.providers.docker import DockerSandboxProvider
from src.sandbox.workspace_layout import workspace_task_scratch_path

SMOKE_COMMAND = (
    "PYTHON_BIN=$(command -v python || command -v python3) && "
    "\"$PYTHON_BIN\" -c \"import json, platform, statistics; "
    "data=[2,4,6,8]; "
    "print(json.dumps({'ok': True, 'mean': statistics.mean(data), "
    "'python': platform.python_version(), 'engine': 'lead_agent_docker_sandbox'}, "
    "ensure_ascii=False, sort_keys=True))\""
)


class SandboxJobRunner:
    """Create sandbox jobs and delegate environment/session execution details."""

    def __init__(
        self,
        *,
        provider: DockerSandboxProvider | None = None,
        manager: WorkspaceSandboxManager | None = None,
        installer: SandboxEnvironmentInstaller | None = None,
        collector: SandboxArtifactCollector | None = None,
        session: SandboxRuntimeSession | None = None,
        script_executor: SandboxScriptExecutor | None = None,
    ) -> None:
        self.session = session or SandboxRuntimeSession(provider=provider, manager=manager)
        self.collector = collector or SandboxArtifactCollector()
        self.script_executor = script_executor or SandboxScriptExecutor(installer=installer)

    async def run_smoke_check(
        self,
        *,
        workspace_id: str,
        workspace_type: str | None = None,
        execution_id: str,
        node_id: str,
        sandbox_policy: Mapping[str, Any],
        billing_reservation_id: str | None = None,
    ) -> dict[str, Any]:
        ctx = await self.session.build_context(
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            sandbox_policy=sandbox_policy,
        )
        command_audit = audit_command(
            HarnessCommand(
                shell_command=SMOKE_COMMAND,
                operation="smoke_check",
                billable=True,
            ),
            CommandAuditPolicy(allow_shell=True),
        )
        require_command_policy_allowed(command_audit)
        job = await ctx.manager.create_job(
            workspace_id=workspace_id,
            environment_id=str(ctx.environment.id),
            execution_id=execution_id,
            node_id=node_id,
            operation="smoke_check",
            billable=True,
            command=SMOKE_COMMAND,
            runtime_image=ctx.runtime_image,
            sandbox_policy=dict(sandbox_policy),
            resource_limits=dict(ctx.limits),
            metadata=_runtime_job_metadata(
                billing_reservation_id=billing_reservation_id,
                command_audit=command_audit.model_dump(),
            ),
            network_policy="none",
        )

        try:
            async with self.session.leased_sandbox(
                ctx=ctx,
                workspace_id=workspace_id,
                execution_id=execution_id,
                job_id=str(job.id),
            ) as sandbox:
                result = await sandbox.execute_command(
                    SMOKE_COMMAND,
                    timeout=ctx.sandbox_timeout,
                    network_profile="none",
                )
        except Exception as exc:
            await mark_job_failed(
                ctx.manager,
                str(job.id),
                exit_code=exception_exit_code_for_job(exc, str(job.id)),
                error_text=str(exc) or type(exc).__name__,
            )
            raise

        output = self.collector.smoke_output(
            result=result,
            workspace_id=workspace_id,
            execution_id=execution_id,
            node_id=node_id,
            runtime_image=ctx.runtime_image,
            provider_image=provider_image(ctx.provider),
            environment_id=str(ctx.environment.id),
            job_id=str(job.id),
        )
        if not result.success:
            output["status"] = "failed"
            await ctx.manager.update_job(
                str(job.id),
                status="failed",
                exit_code=result.exit_code,
                error_text=output["stderr"] or None,
            )
            raise SandboxCommandExecutionError(
                "Docker sandbox Python smoke check failed "
                f"(exit_code={result.exit_code}, stderr={output['stderr'] or 'none'})",
                output=output,
            )

        await ctx.manager.update_job(str(job.id), status="succeeded", exit_code=result.exit_code)
        return output

    async def run_python_script(
        self,
        *,
        workspace_id: str,
        workspace_type: str | None = None,
        execution_id: str,
        node_id: str,
        sandbox_policy: Mapping[str, Any],
        script: str,
        script_name: str = "analysis.py",
        dependency_hints: list[str] | str | None = None,
        dataset_provenance: list[dict[str, Any]] | None = None,
        billing_reservation_id: str | None = None,
    ) -> dict[str, Any]:
        plan = self.script_executor.build_plan(
            script=script,
            script_name=script_name,
            dependency_hints=dependency_hints,
        )
        ctx = await self.session.build_context(
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            sandbox_policy=sandbox_policy,
        )
        task_scratch_path = workspace_task_scratch_path(
            execution_id=execution_id,
            node_id=node_id,
        )
        execution_env = sandbox_script_execution_env(task_scratch_path)
        command_audit_result = audit_command(
            HarnessCommand(
                argv=plan.command_argv,
                cwd=task_scratch_path,
                env=execution_env,
                operation="run_python",
                billable=True,
            ),
            CommandAuditPolicy(allowed_network_profiles=("none",)),
        )
        require_command_policy_allowed(command_audit_result)
        command_audit = command_audit_result.model_dump()
        execution_lifecycle = build_sandbox_execution_lifecycle(
            status="queued",
            operation="run_python",
            workspace_id=workspace_id,
            execution_id=execution_id,
            node_id=node_id,
            environment_id=str(ctx.environment.id),
            runtime_image=ctx.runtime_image,
            provider_image=provider_image(ctx.provider),
            command_preview=plan.command,
            command_argv=plan.command_argv,
            cwd=task_scratch_path,
            env=execution_env,
            network_profile="none",
            timeout_seconds=ctx.sandbox_timeout,
        )
        job_metadata = _runtime_job_metadata(
            script_name=plan.safe_name,
            billing_reservation_id=billing_reservation_id,
            command_audit=command_audit,
            task_scratch_path=task_scratch_path,
            execution_lifecycle=execution_lifecycle,
        )
        job = await ctx.manager.create_job(
            workspace_id=workspace_id,
            environment_id=str(ctx.environment.id),
            execution_id=execution_id,
            node_id=node_id,
            operation="run_python",
            billable=True,
            command=plan.command,
            runtime_image=ctx.runtime_image,
            sandbox_policy=dict(sandbox_policy),
            resource_limits=dict(ctx.limits),
            metadata=job_metadata,
            script_hash=plan.script_hash,
            network_policy="none",
        )

        try:
            async with self.session.leased_sandbox(
                ctx=ctx,
                workspace_id=workspace_id,
                execution_id=execution_id,
                job_id=str(job.id),
            ) as sandbox:
                synced_dataset_provenance = await sync_dataset_manifest(
                    sandbox=sandbox,
                    dataset_provenance=dataset_provenance,
                )
                script_state = await self.script_executor.execute(
                    sandbox=sandbox,
                    ctx=ctx,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    node_id=node_id,
                    run_job_id=str(job.id),
                    sandbox_policy=dict(sandbox_policy),
                    plan=plan,
                )
                stdout_budget, stderr_budget = await budget_script_streams(
                    sandbox=sandbox,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    node_id=node_id,
                    sandbox_policy=sandbox_policy,
                    stdout=script_state.result.stdout.strip(),
                    stderr=script_state.result.stderr.strip(),
                )
                generated_artifacts = await discover_generated_artifacts(sandbox)
        except Exception as exc:
            failed_exit_code = exception_exit_code_for_job(exc, str(job.id))
            failed_lifecycle = finalize_sandbox_execution_lifecycle(
                execution_lifecycle,
                sandbox_job_id=str(job.id),
                status="failed",
                exit_code=failed_exit_code,
                stdout_externalized=False,
                stderr_externalized=False,
                output_refs=[],
                generated_artifacts=[],
            )
            await mark_job_failed(
                ctx.manager,
                str(job.id),
                exit_code=failed_exit_code,
                error_text=str(exc) or type(exc).__name__,
                metadata_json={
                    **job_metadata,
                    "execution_lifecycle": failed_lifecycle,
                },
            )
            raise

        output = self.collector.script_output(
            result=script_state.result,
            workspace_id=workspace_id,
            execution_id=execution_id,
            node_id=node_id,
            safe_name=plan.safe_name,
            script_hash=plan.script_hash,
            runtime_image=ctx.runtime_image,
            provider_image=provider_image(ctx.provider),
            environment_id=str(ctx.environment.id),
            job_id=str(job.id),
            dependency_hints=plan.dependency_hints,
            installed_packages=script_state.installed_packages,
            install_job_ids=script_state.install_job_ids,
            command_audit=command_audit,
            install_command_audits=script_state.install_command_audits,
            retry_count=script_state.retry_count,
            script_path=plan.script_path,
            task_scratch_path=script_state.task_scratch_path,
            stdout_preview=stdout_budget.preview_text if stdout_budget.truncated else None,
            stderr_preview=stderr_budget.preview_text if stderr_budget.truncated else None,
            stdout_ref=stdout_budget.output_refs[0] if stdout_budget.output_refs else None,
            stderr_ref=stderr_budget.output_refs[0] if stderr_budget.output_refs else None,
            generated_artifacts=generated_artifacts,
            dataset_provenance=synced_dataset_provenance,
        )
        final_lifecycle = finalize_sandbox_execution_lifecycle(
            execution_lifecycle,
            sandbox_job_id=str(job.id),
            status="failed" if not script_state.result.success else "succeeded",
            exit_code=script_state.result.exit_code,
            stdout_externalized=bool(output.get("stdout_externalized")),
            stderr_externalized=bool(output.get("stderr_externalized")),
            output_refs=[str(ref) for ref in output.get("output_refs") or [] if str(ref).strip()],
            generated_artifacts=generated_artifacts,
        )
        output["execution_lifecycle"] = final_lifecycle
        final_job_metadata = {
            **job_metadata,
            "execution_lifecycle": final_lifecycle,
        }
        if not script_state.result.success:
            output["status"] = "failed"
            await ctx.manager.update_job(
                str(job.id),
                status="failed",
                exit_code=script_state.result.exit_code,
                error_text=output["stderr"] or None,
                metadata_json=final_job_metadata,
            )
            raise SandboxCommandExecutionError(
                "Docker sandbox Python script failed "
                f"(exit_code={script_state.result.exit_code}, stderr={output['stderr'] or 'none'})",
                output=output,
            )

        await ctx.manager.update_job(
            str(job.id),
            status="succeeded",
            exit_code=script_state.result.exit_code,
            metadata_json=final_job_metadata,
        )
        return output


def _runtime_job_metadata(
    *,
    script_name: str | None = None,
    billing_reservation_id: str | None = None,
    command_audit: dict[str, Any] | None = None,
    task_scratch_path: str | None = None,
    execution_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {"source": "lead_agent_sandbox_runtime"}
    if script_name is not None:
        metadata["script_name"] = script_name
    if task_scratch_path:
        metadata["task_scratch_path"] = task_scratch_path
    if billing_reservation_id:
        metadata["credit_reservation_id"] = billing_reservation_id
    if command_audit is not None:
        metadata["command_audit"] = command_audit
    if execution_lifecycle is not None:
        metadata["execution_lifecycle"] = execution_lifecycle
    return metadata
