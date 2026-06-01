"""Python script execution flow for lead-agent sandbox jobs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from src.agents.lead_agent.v2.sandbox_environment_installer import SandboxEnvironmentInstaller
from src.agents.lead_agent.v2.sandbox_errors import SandboxCommandExecutionError
from src.agents.lead_agent.v2.sandbox_runtime_session import SandboxRuntimeContext
from src.agents.lead_agent.v2.workspace_sandbox import (
    WORKSPACE_VENV_PYTHON,
    detect_missing_python_module,
    normalize_dependency_hints,
    resolve_package_for_missing_module,
)

SCRIPT_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
MAX_SCRIPT_BYTES = 128 * 1024


@dataclass(frozen=True)
class SandboxScriptPlan:
    """Validated script execution plan."""

    script: str
    dependency_hints: list[str]
    safe_name: str
    script_path: str
    script_hash: str
    command: str


@dataclass(frozen=True)
class SandboxScriptExecutionState:
    """Script process result plus installation side effects."""

    result: Any
    installed_packages: list[str]
    install_job_ids: list[str]
    retry_count: int


class SandboxScriptExecutor:
    """Ensure Python, install allowed packages, run script, and retry once."""

    def __init__(self, *, installer: SandboxEnvironmentInstaller | None = None) -> None:
        self.installer = installer or SandboxEnvironmentInstaller()

    def build_plan(
        self,
        *,
        script: str,
        script_name: str,
        dependency_hints: list[str] | str | None,
    ) -> SandboxScriptPlan:
        script_bytes = _validate_script(script)
        safe_name = _safe_script_name(script_name)
        script_path = f"/workspace/scripts/{safe_name}"
        return SandboxScriptPlan(
            script=script,
            dependency_hints=normalize_dependency_hints(dependency_hints),
            safe_name=safe_name,
            script_path=script_path,
            script_hash=hashlib.sha256(script_bytes).hexdigest(),
            command=f"{WORKSPACE_VENV_PYTHON} {script_path}",
        )

    async def execute(
        self,
        *,
        sandbox: Any,
        ctx: SandboxRuntimeContext,
        workspace_id: str,
        execution_id: str,
        node_id: str,
        run_job_id: str,
        sandbox_policy: dict[str, Any],
        plan: SandboxScriptPlan,
    ) -> SandboxScriptExecutionState:
        await self._ensure_python_runtime(
            sandbox=sandbox,
            ctx=ctx,
            run_job_id=run_job_id,
            plan=plan,
        )
        installed_packages, install_job_ids = await self._install_declared_dependencies(
            sandbox=sandbox,
            ctx=ctx,
            workspace_id=workspace_id,
            execution_id=execution_id,
            node_id=node_id,
            run_job_id=run_job_id,
            sandbox_policy=sandbox_policy,
            dependency_hints=plan.dependency_hints,
        )
        await sandbox.write_file(plan.script_path, plan.script)
        result = await sandbox.execute_command(
            plan.command,
            timeout=ctx.sandbox_timeout,
            network_profile="none",
        )
        retry_count, final_result = await self._retry_missing_dependency_once(
            sandbox=sandbox,
            ctx=ctx,
            workspace_id=workspace_id,
            execution_id=execution_id,
            node_id=node_id,
            run_job_id=run_job_id,
            sandbox_policy=sandbox_policy,
            command=plan.command,
            dependency_hints=plan.dependency_hints,
            installed_packages=installed_packages,
            install_job_ids=install_job_ids,
            result=result,
        )
        return SandboxScriptExecutionState(
            result=final_result,
            installed_packages=installed_packages,
            install_job_ids=install_job_ids,
            retry_count=retry_count,
        )

    async def _ensure_python_runtime(
        self,
        *,
        sandbox: Any,
        ctx: SandboxRuntimeContext,
        run_job_id: str,
        plan: SandboxScriptPlan,
    ) -> None:
        setup_result = await self.installer.ensure_python_environment(sandbox, timeout=ctx.sandbox_timeout)
        if setup_result.success:
            return
        await _raise_setup_failure(
            manager=ctx.manager,
            job_id=run_job_id,
            result=setup_result,
            runtime_image=ctx.runtime_image,
            environment_id=str(ctx.environment.id),
            script_path=plan.script_path,
            safe_name=plan.safe_name,
            script_hash=plan.script_hash,
        )

    async def _install_declared_dependencies(
        self,
        *,
        sandbox: Any,
        ctx: SandboxRuntimeContext,
        workspace_id: str,
        execution_id: str,
        node_id: str,
        run_job_id: str,
        sandbox_policy: dict[str, Any],
        dependency_hints: list[str],
    ) -> tuple[list[str], list[str]]:
        installed_packages: list[str] = []
        install_job_ids: list[str] = []
        if not dependency_hints:
            return installed_packages, install_job_ids
        packages, install_job_id = await self._install_dependency_packages(
            sandbox=sandbox,
            ctx=ctx,
            workspace_id=workspace_id,
            execution_id=execution_id,
            node_id=node_id,
            run_job_id=run_job_id,
            sandbox_policy=sandbox_policy,
            packages=dependency_hints,
            reason="declared_hints",
        )
        installed_packages.extend(packages)
        install_job_ids.append(install_job_id)
        return installed_packages, install_job_ids

    async def _retry_missing_dependency_once(
        self,
        *,
        sandbox: Any,
        ctx: SandboxRuntimeContext,
        workspace_id: str,
        execution_id: str,
        node_id: str,
        run_job_id: str,
        sandbox_policy: dict[str, Any],
        command: str,
        dependency_hints: list[str],
        installed_packages: list[str],
        install_job_ids: list[str],
        result: Any,
    ) -> tuple[int, Any]:
        missing_package = _resolve_missing_package(result, dependency_hints)
        if (
            result.success
            or not missing_package
            or not self.installer.package_not_installed(missing_package, installed_packages)
        ):
            return 0, result
        packages, install_job_id = await self._install_dependency_packages(
            sandbox=sandbox,
            ctx=ctx,
            workspace_id=workspace_id,
            execution_id=execution_id,
            node_id=node_id,
            run_job_id=run_job_id,
            sandbox_policy=sandbox_policy,
            packages=[missing_package],
            reason="missing_module_retry",
        )
        installed_packages.extend(packages)
        install_job_ids.append(install_job_id)
        retry_result = await sandbox.execute_command(
            command,
            timeout=ctx.sandbox_timeout,
            network_profile="none",
        )
        return 1, retry_result

    async def _install_dependency_packages(
        self,
        *,
        sandbox: Any,
        ctx: SandboxRuntimeContext,
        workspace_id: str,
        execution_id: str,
        node_id: str,
        run_job_id: str,
        sandbox_policy: dict[str, Any],
        packages: list[str],
        reason: str,
    ) -> tuple[list[str], str]:
        return await self.installer.install_dependencies(
            sandbox=sandbox,
            manager=ctx.manager,
            workspace_id=workspace_id,
            environment_id=str(ctx.environment.id),
            execution_id=execution_id,
            node_id=node_id,
            run_job_id=run_job_id,
            sandbox_policy=sandbox_policy,
            resource_limits=dict(ctx.limits),
            runtime_image=ctx.runtime_image,
            packages=packages,
            reason=reason,
            timeout=ctx.sandbox_timeout,
        )


async def _raise_setup_failure(
    *,
    manager: Any,
    job_id: str,
    result: Any,
    runtime_image: str,
    environment_id: str,
    script_path: str,
    safe_name: str,
    script_hash: str,
) -> None:
    stderr = result.stderr.strip()
    await manager.update_job(
        str(job_id),
        status="failed",
        exit_code=result.exit_code,
        error_text=stderr or None,
    )
    raise SandboxCommandExecutionError(
        "Docker sandbox Python environment setup failed "
        f"(exit_code={result.exit_code}, stderr={stderr or 'none'})",
        output={
            "status": "failed",
            "operation": "python_script",
            "stdout": result.stdout.strip(),
            "stderr": stderr,
            "exit_code": result.exit_code,
            "docker_image": runtime_image,
            "sandbox_environment_id": environment_id,
            "sandbox_job_id": str(job_id),
            "script_path": script_path,
            "script_name": safe_name,
            "script_hash": script_hash,
        },
    )


def _validate_script(script: str) -> bytes:
    if not isinstance(script, str) or not script.strip():
        raise ValueError("sandbox_python python_script requires a non-empty script")
    script_bytes = script.encode("utf-8")
    if len(script_bytes) > MAX_SCRIPT_BYTES:
        raise ValueError("sandbox_python script exceeds 128 KiB limit")
    return script_bytes


def _safe_script_name(value: str) -> str:
    name = SCRIPT_NAME_RE.sub("_", str(value or "").strip())
    if not name or name in {".", ".."}:
        name = "analysis.py"
    if not name.endswith(".py"):
        name = f"{name}.py"
    return name[:80]


def _resolve_missing_package(result: Any, dependency_hints: list[str]) -> str | None:
    missing_module = detect_missing_python_module("\n".join([result.stderr, result.stdout]))
    return resolve_package_for_missing_module(missing_module, dependency_hints) if missing_module else None
