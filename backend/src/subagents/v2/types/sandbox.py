"""Sandbox-backed deterministic subagents."""

from __future__ import annotations

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent
from src.agents.lead_agent.v2.sandbox_runtime import run_python_script, run_python_smoke_check


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
        await ctx.emit("thinking", "正在启动隔离 Docker sandbox 运行受控 Python 任务。")
        if operation == "smoke_check":
            output = await run_python_smoke_check(
                workspace_id=ctx.workspace_id,
                execution_id=ctx.execution_id,
                node_id=node_id,
                sandbox_policy=sandbox_policy,
            )
        else:
            output = await run_python_script(
                workspace_id=ctx.workspace_id,
                execution_id=ctx.execution_id,
                node_id=node_id,
                sandbox_policy=sandbox_policy,
                script=str(ctx.inputs.get("script") or ""),
                script_name=str(ctx.inputs.get("script_name") or "analysis.py"),
            )
        await ctx.emit("thinking", "Docker sandbox Python 任务完成，正在整理结果。")
        return SubagentResult(
            output=output,
            thinking="Lead Agent subagent used Docker sandbox to run a controlled Python task.",
            tool_calls=[
                {
                    "name": "sandbox.run_python",
                    "args": {
                        "operation": operation,
                        "script_hash": output.get("script_hash"),
                    },
                    "status": output["status"],
                    "exit_code": output["exit_code"],
                    "docker_image": output["docker_image"],
                }
            ],
            token_usage={"input": 0, "output": 0},
        )
