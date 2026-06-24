"""Sandbox-backed deterministic subagents."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta

from src.agents.lead_agent.v2.sandbox_runtime import (
    SandboxCommandExecutionError,
    require_run_python_allowed,
    run_python_script,
    run_python_smoke_check,
)
from src.services.credit_service import CreditService

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent

_SANDBOX_RESERVATION_TTL = timedelta(hours=1)


def _sandbox_python_output_identifier(output: dict, key: str) -> str | None:
    value = output.get(key)
    if value:
        text = str(value).strip()
        if text:
            return text
    execution_manifest = output.get("execution_manifest")
    if isinstance(execution_manifest, dict):
        value = execution_manifest.get(key)
        if value:
            text = str(value).strip()
            if text:
                return text
    return None


def _sandbox_python_generated_artifacts(output: dict) -> list[object]:
    raw_artifacts = output.get("generated_artifacts") or []
    if not raw_artifacts:
        return []

    sandbox_job_id = _sandbox_python_output_identifier(output, "sandbox_job_id")
    sandbox_environment_id = _sandbox_python_output_identifier(output, "sandbox_environment_id")
    generated_artifacts: list[object] = []
    for artifact in raw_artifacts:
        if not isinstance(artifact, dict):
            generated_artifacts.append(artifact)
            continue
        copied = dict(artifact)
        if sandbox_job_id and not copied.get("sandbox_job_id"):
            copied["sandbox_job_id"] = sandbox_job_id
        if sandbox_environment_id and not copied.get("sandbox_environment_id"):
            copied["sandbox_environment_id"] = sandbox_environment_id
        generated_artifacts.append(copied)
    return generated_artifacts


def _sandbox_python_tool_call(
    *,
    operation: str,
    output: dict,
    billing: dict,
) -> dict:
    generated_artifacts = _sandbox_python_generated_artifacts(output)
    metadata: dict[str, object] = {}
    for key in (
        "execution_manifest",
        "reproducibility_manifest",
        "experiment_narrative",
        "failure_classification",
        "execution_lifecycle",
        "command_audit",
        "install_command_audits",
    ):
        value = output.get(key)
        if value:
            metadata[key] = value
    if output.get("error_code"):
        metadata["error_code"] = output["error_code"]
    if generated_artifacts:
        metadata["generated_artifacts"] = generated_artifacts

    call = {
        "name": "sandbox.run_python",
        "args": {
            "operation": operation,
            "script_hash": output.get("script_hash"),
        },
        "status": output.get("status") or "completed",
        "exit_code": output.get("exit_code"),
        "docker_image": output.get("docker_image"),
        "billing": billing,
        "metadata": metadata,
    }
    if generated_artifacts:
        call["generated_artifacts"] = generated_artifacts
    output_refs = [str(ref) for ref in output.get("output_refs") or [] if str(ref).strip()]
    if output_refs:
        call["output_refs"] = output_refs
        metadata["output_refs"] = output_refs
    return call


@subagent("sandbox_python")
class SandboxPythonSubagent(SubagentBase):
    """Run controlled Python operations in the Lead Agent Docker sandbox."""

    allowed_tools = ["sandbox.run_python"]

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        operation = str(ctx.inputs.get("operation") or "smoke_check")
        if operation not in {"smoke_check", "python_script"}:
            raise ValueError(f"unsupported sandbox_python operation: {operation}")

        node_id = str(ctx.inputs.get("node_id") or "sandbox_python")
        sandbox_policy = dict(ctx.capability_policy.get("sandbox_policy") or {})
        require_run_python_allowed(sandbox_policy)
        user_id = str(ctx.inputs.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("sandbox billing requires user_id")

        credit_service = CreditService()
        estimated_credits = await credit_service.estimate_sandbox_reservation_credits(
            operation="run_python",
            sandbox_policy=sandbox_policy,
        )
        reservation = await credit_service.reserve_for_sandbox_operation(
            user_id=user_id,
            workspace_id=ctx.workspace_id,
            execution_id=ctx.execution_id,
            node_id=node_id,
            operation="run_python",
            estimated_credits=estimated_credits,
            expires_at=datetime.now(UTC) + _SANDBOX_RESERVATION_TTL,
            metadata={"source": "sandbox_python_subagent"},
        )
        await ctx.emit("thinking", "正在启动隔离 Docker sandbox 运行受控 Python 任务。")
        started = time.perf_counter()

        async def _settle_billing() -> dict:
            duration_seconds = max(int(math.ceil(time.perf_counter() - started)), 0)
            settled_credits = await credit_service.estimate_sandbox_settlement_credits(
                operation="run_python",
                sandbox_policy=sandbox_policy,
                duration_seconds=duration_seconds,
            )
            _settled_reservation, tx = await credit_service.settle_sandbox_reservation(
                reservation_id=str(reservation.id),
                settled_credits=settled_credits,
                operation="run_python",
                task_id=ctx.execution_id,
                metadata={
                    "node_id": node_id,
                    "duration_seconds": duration_seconds,
                    "source": "sandbox_python_subagent",
                },
            )
            return {
                "type": "sandbox_operation_billing",
                "operation": "run_python",
                "credits_charged": settled_credits,
                "credit_reservation_id": str(reservation.id),
                "transaction_id": str(tx.id) if tx is not None else None,
                "balance_after": int(getattr(tx, "balance_after", 0) or 0) if tx is not None else None,
                "charged": settled_credits > 0,
            }

        try:
            if operation == "smoke_check":
                output = await run_python_smoke_check(
                    workspace_id=ctx.workspace_id,
                    workspace_type=str(ctx.inputs.get("workspace_type") or ""),
                    execution_id=ctx.execution_id,
                    node_id=node_id,
                    sandbox_policy=sandbox_policy,
                    billing_reservation_id=str(reservation.id),
                )
            else:
                output = await run_python_script(
                    workspace_id=ctx.workspace_id,
                    workspace_type=str(ctx.inputs.get("workspace_type") or ""),
                    execution_id=ctx.execution_id,
                    node_id=node_id,
                    sandbox_policy=sandbox_policy,
                    script=str(ctx.inputs.get("script") or ""),
                    script_name=str(ctx.inputs.get("script_name") or "analysis.py"),
                    dependency_hints=ctx.inputs.get("dependency_hints"),
                    billing_reservation_id=str(reservation.id),
                )
        except SandboxCommandExecutionError:
            await _settle_billing()
            raise
        except Exception:
            await credit_service.release_reservation(
                str(reservation.id),
                reason="sandbox execution failed before settlement",
            )
            raise
        billing_metadata = await _settle_billing()
        output = dict(output)
        output["billing"] = billing_metadata
        await ctx.emit("thinking", "Docker sandbox Python 任务完成，正在整理结果。")
        return SubagentResult(
            output=output,
            thinking="Lead Agent subagent used Docker sandbox to run a controlled Python task.",
            tool_calls=[
                _sandbox_python_tool_call(operation=operation, output=output, billing=billing_metadata)
            ],
            token_usage={"input": 0, "output": 0},
        )
