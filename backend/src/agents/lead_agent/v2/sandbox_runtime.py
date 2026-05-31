"""Lead-agent owned sandbox execution helpers.

Only the right-side LeadAgentRuntime/subagent path should import this module.
The left chat agent may launch capabilities, but must not acquire or execute a
sandbox directly.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from src.agents.lead_agent.v2.workspace_sandbox import (
    ENSURE_WORKSPACE_VENV_COMMAND,
    WORKSPACE_VENV_PYTHON,
    WorkspaceSandboxManager,
    build_pip_install_command,
    detect_missing_python_module,
    install_policy_snapshot,
    normalize_dependency_hints,
    policy_allows_package_install,
    resolve_package_for_missing_module,
    workspace_provider_key,
)
from src.sandbox.base import CommandResult, Sandbox
from src.sandbox.providers.docker import DockerSandboxProvider

_SMOKE_COMMAND = (
    "python -c \"import json, platform, statistics; "
    "data=[2,4,6,8]; "
    "print(json.dumps({'ok': True, 'mean': statistics.mean(data), "
    "'python': platform.python_version(), 'engine': 'lead_agent_docker_sandbox'}, "
    "ensure_ascii=False, sort_keys=True))\""
)
_SCRIPT_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_MAX_SCRIPT_BYTES = 128 * 1024


class SandboxCommandExecutionError(RuntimeError):
    """Raised when user code ran in sandbox but exited unsuccessfully."""

    def __init__(self, message: str, *, output: dict[str, Any]) -> None:
        super().__init__(message)
        self.output = output


def _default_base_dir() -> str:
    configured = os.getenv("WENJIN_AGENT_SANDBOX_BASE_DIR")
    if configured:
        return configured

    latex_dir = os.getenv("WENJIN_LATEX_DATA_DIR")
    if latex_dir:
        return str(Path(latex_dir).expanduser().resolve().parent / "agent_sandboxes")

    return str((Path.cwd() / ".wenjin" / "agent_sandboxes").resolve())


def _default_image() -> str:
    return os.getenv(
        "WENJIN_AGENT_SANDBOX_IMAGE",
        "docker.m.daocloud.io/library/python:3.13-slim",
    )


def _resource_limits(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    limits = policy.get("resource_limits")
    return limits if isinstance(limits, Mapping) else {}


def require_run_python_allowed(policy: Mapping[str, Any]) -> None:
    """Raise when the capability policy does not allow Python sandbox execution."""
    mode = str(policy.get("mode") or "none")
    allowed = {str(item) for item in policy.get("allowed_operations") or []}
    if mode not in {"required", "optional", "conditional"} or "run_python" not in allowed:
        raise PermissionError("capability sandbox_policy does not allow run_python")


def _provider_from_policy(policy: Mapping[str, Any]) -> DockerSandboxProvider:
    limits = _resource_limits(policy)
    memory_mb = int(limits.get("memory_mb") or os.getenv("WENJIN_AGENT_SANDBOX_MEMORY_MB") or 512)
    cpu_limit = int(limits.get("cpu") or os.getenv("WENJIN_AGENT_SANDBOX_CPU") or 1)
    timeout_seconds = int(limits.get("timeout_seconds") or 120)
    return DockerSandboxProvider(
        base_dir=_default_base_dir(),
        image=_default_image(),
        timeout=timeout_seconds,
        memory=f"{memory_mb}m",
        cpu_limit=cpu_limit,
    )


def _provider_image(provider: DockerSandboxProvider) -> str | None:
    value = getattr(provider, "image", None)
    return str(value) if value else None


def _runtime_job_metadata(
    *,
    script_name: str | None = None,
    billing_reservation_id: str | None = None,
) -> dict[str, Any]:
    metadata = {"source": "lead_agent_sandbox_runtime"}
    if script_name is not None:
        metadata["script_name"] = script_name
    if billing_reservation_id:
        metadata["credit_reservation_id"] = billing_reservation_id
    return metadata


async def _ensure_python_environment(
    sandbox: Sandbox,
    *,
    timeout: int,
) -> CommandResult:
    return await sandbox.execute_command(
        ENSURE_WORKSPACE_VENV_COMMAND,
        timeout=timeout,
        network_profile="none",
    )


async def _install_dependencies(
    *,
    sandbox: Sandbox,
    manager: WorkspaceSandboxManager,
    workspace_id: str,
    environment_id: str,
    execution_id: str,
    node_id: str,
    run_job_id: str,
    sandbox_policy: dict[str, Any],
    resource_limits: dict[str, Any],
    runtime_image: str,
    packages: list[str],
    reason: str,
    timeout: int,
) -> tuple[list[str], str]:
    if not policy_allows_package_install(sandbox_policy):
        raise PermissionError("capability sandbox_policy does not allow package installation")

    normalized_packages = normalize_dependency_hints(packages)
    command = build_pip_install_command(normalized_packages)
    install_job = await manager.create_job(
        workspace_id=workspace_id,
        environment_id=environment_id,
        execution_id=execution_id,
        node_id=node_id,
        operation="install_dependencies",
        billable=False,
        command=command,
        runtime_image=runtime_image,
        sandbox_policy=install_policy_snapshot(sandbox_policy),
        resource_limits=resource_limits,
        metadata={
            "source": "lead_agent_sandbox_runtime",
            "run_job_id": run_job_id,
            "reason": reason,
            "packages": normalized_packages,
        },
        network_policy="package_index_only",
    )
    await manager.update_job(str(install_job.id), status="running")
    result = await sandbox.execute_command(
        command,
        timeout=timeout,
        network_profile="package_index_only",
    )
    if not result.success:
        stderr = result.stderr.strip()
        await manager.update_job(
            str(install_job.id),
            status="failed",
            exit_code=result.exit_code,
            error_text=stderr or None,
        )
        raise SandboxCommandExecutionError(
            "Docker sandbox dependency installation failed "
            f"(exit_code={result.exit_code}, stderr={stderr or 'none'})",
            output={
                "status": "failed",
                "operation": "install_dependencies",
                "packages": normalized_packages,
                "stdout": result.stdout.strip(),
                "stderr": stderr,
                "exit_code": result.exit_code,
                "sandbox_environment_id": environment_id,
                "sandbox_job_id": str(install_job.id),
            },
        )

    await manager.update_job(str(install_job.id), status="succeeded", exit_code=result.exit_code)
    return normalized_packages, str(install_job.id)


async def _mark_job_failed(
    manager: WorkspaceSandboxManager,
    job_id: str,
    *,
    exit_code: int | None = None,
    error_text: str | None = None,
) -> None:
    with suppress(Exception):
        await manager.update_job(
            str(job_id),
            status="failed",
            exit_code=exit_code,
            error_text=error_text,
        )


def _exception_exit_code_for_job(exc: Exception, job_id: str) -> int | None:
    if not isinstance(exc, SandboxCommandExecutionError):
        return None
    output = exc.output if isinstance(exc.output, dict) else {}
    if str(output.get("sandbox_job_id") or "") != str(job_id):
        return None
    try:
        return int(output.get("exit_code"))
    except (TypeError, ValueError):
        return None


async def run_python_smoke_check(
    *,
    workspace_id: str,
    execution_id: str,
    node_id: str,
    sandbox_policy: Mapping[str, Any],
    provider: DockerSandboxProvider | None = None,
    manager: WorkspaceSandboxManager | None = None,
    billing_reservation_id: str | None = None,
) -> dict[str, Any]:
    """Run the controlled Python smoke calculation in a Docker sandbox."""

    require_run_python_allowed(sandbox_policy)
    limits = _resource_limits(sandbox_policy)
    timeout_seconds = int(limits.get("timeout_seconds") or 120)
    sandbox_timeout = max(1, min(timeout_seconds, 120))
    resolved_provider = provider or _provider_from_policy(sandbox_policy)
    runtime_image = _provider_image(resolved_provider) or _default_image()
    resolved_manager = manager or WorkspaceSandboxManager()
    environment = await resolved_manager.get_or_create_environment(
        workspace_id=workspace_id,
        sandbox_policy=dict(sandbox_policy),
        resource_limits=dict(limits),
        runtime_image=runtime_image,
    )
    sandbox_key = str(
        getattr(environment, "sandbox_id", None)
        or getattr(environment, "metadata_json", {}).get("provider_key")
        or workspace_provider_key(workspace_id)
    )
    job = await resolved_manager.create_job(
        workspace_id=workspace_id,
        environment_id=str(environment.id),
        execution_id=execution_id,
        node_id=node_id,
        operation="smoke_check",
        billable=True,
        command=_SMOKE_COMMAND,
        runtime_image=runtime_image,
        sandbox_policy=dict(sandbox_policy),
        resource_limits=dict(limits),
        metadata=_runtime_job_metadata(billing_reservation_id=billing_reservation_id),
        network_policy="none",
    )

    lease_token: str | None = None
    sandbox = None
    try:
        lease_token = await resolved_manager.acquire_lease(
            workspace_id=workspace_id,
            environment_id=str(environment.id),
            job_id=str(job.id),
            execution_id=execution_id,
            ttl_seconds=max(sandbox_timeout + 60, 120),
        )
        sandbox = await resolved_provider.acquire(sandbox_key)
        await resolved_manager.update_job(str(job.id), status="running")
        result = await sandbox.execute_command(
            _SMOKE_COMMAND,
            timeout=sandbox_timeout,
            network_profile="none",
        )
    except Exception as exc:
        await _mark_job_failed(
            resolved_manager,
            str(job.id),
            exit_code=_exception_exit_code_for_job(exc, str(job.id)),
            error_text=str(exc) or type(exc).__name__,
        )
        raise
    finally:
        if sandbox is not None:
            with suppress(Exception):
                await resolved_provider.release(sandbox)
        if lease_token is not None:
            with suppress(Exception):
                await resolved_manager.release_lease(
                    workspace_id=workspace_id,
                    lease_token=lease_token,
                )

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    parsed: dict[str, Any] = {}
    if stdout:
        try:
            loaded = json.loads(stdout)
            parsed = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            parsed = {}

    mean = parsed.get("mean")
    python_version = parsed.get("python")
    report_markdown = (
        "# 内部实验环境自检\n\n"
        "- 执行位置：LeadAgentRuntime / subagent node\n"
        "- 隔离方式：Docker sandbox\n"
        f"- Workspace：{workspace_id}\n"
        f"- Execution：{execution_id}\n"
        f"- Node：{node_id}\n"
        f"- Python：{python_version}\n"
        f"- 固定计算 mean([2,4,6,8])：{mean}\n"
        f"- Docker image：{getattr(resolved_provider, 'image', None)}\n"
    )
    output = {
        "status": "completed",
        "operation": "smoke_check",
        "mean": mean,
        "python": python_version,
        "engine": parsed.get("engine"),
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": result.exit_code,
        "docker_image": runtime_image,
        "sandbox_environment_id": str(environment.id),
        "sandbox_job_id": str(job.id),
        "report_markdown": report_markdown,
    }
    if not result.success:
        output["status"] = "failed"
        await resolved_manager.update_job(
            str(job.id),
            status="failed",
            exit_code=result.exit_code,
            error_text=stderr or None,
        )
        raise SandboxCommandExecutionError(
            "Docker sandbox Python smoke check failed "
            f"(exit_code={result.exit_code}, stderr={stderr or 'none'})",
            output=output,
        )

    await resolved_manager.update_job(str(job.id), status="succeeded", exit_code=result.exit_code)
    return output


async def run_python_script(
    *,
    workspace_id: str,
    execution_id: str,
    node_id: str,
    sandbox_policy: Mapping[str, Any],
    script: str,
    script_name: str = "analysis.py",
    dependency_hints: list[str] | str | None = None,
    provider: DockerSandboxProvider | None = None,
    manager: WorkspaceSandboxManager | None = None,
    billing_reservation_id: str | None = None,
) -> dict[str, Any]:
    """Run a capability-declared Python script in the Docker sandbox."""

    require_run_python_allowed(sandbox_policy)
    if not isinstance(script, str) or not script.strip():
        raise ValueError("sandbox_python python_script requires a non-empty script")
    script_bytes = script.encode("utf-8")
    if len(script_bytes) > _MAX_SCRIPT_BYTES:
        raise ValueError("sandbox_python script exceeds 128 KiB limit")

    normalized_dependency_hints = normalize_dependency_hints(dependency_hints)
    safe_name = _safe_script_name(script_name)
    script_path = f"/workspace/scripts/{safe_name}"
    script_hash = hashlib.sha256(script_bytes).hexdigest()
    limits = _resource_limits(sandbox_policy)
    timeout_seconds = int(limits.get("timeout_seconds") or 120)
    sandbox_timeout = max(1, min(timeout_seconds, 120))
    resolved_provider = provider or _provider_from_policy(sandbox_policy)
    runtime_image = _provider_image(resolved_provider) or _default_image()
    resolved_manager = manager or WorkspaceSandboxManager()
    environment = await resolved_manager.get_or_create_environment(
        workspace_id=workspace_id,
        sandbox_policy=dict(sandbox_policy),
        resource_limits=dict(limits),
        runtime_image=runtime_image,
    )
    sandbox_key = str(
        getattr(environment, "sandbox_id", None)
        or getattr(environment, "metadata_json", {}).get("provider_key")
        or workspace_provider_key(workspace_id)
    )
    command = f"{WORKSPACE_VENV_PYTHON} {script_path}"
    job = await resolved_manager.create_job(
        workspace_id=workspace_id,
        environment_id=str(environment.id),
        execution_id=execution_id,
        node_id=node_id,
        operation="run_python",
        billable=True,
        command=command,
        runtime_image=runtime_image,
        sandbox_policy=dict(sandbox_policy),
        resource_limits=dict(limits),
        metadata=_runtime_job_metadata(
            script_name=safe_name,
            billing_reservation_id=billing_reservation_id,
        ),
        script_hash=script_hash,
        network_policy="none",
    )

    installed_packages: list[str] = []
    install_job_ids: list[str] = []
    retry_count = 0
    lease_token: str | None = None
    sandbox = None
    try:
        lease_token = await resolved_manager.acquire_lease(
            workspace_id=workspace_id,
            environment_id=str(environment.id),
            job_id=str(job.id),
            execution_id=execution_id,
            ttl_seconds=max(sandbox_timeout + 60, 120),
        )
        sandbox = await resolved_provider.acquire(sandbox_key)
        await resolved_manager.update_job(str(job.id), status="running")
        setup_result = await _ensure_python_environment(sandbox, timeout=sandbox_timeout)
        if not setup_result.success:
            stderr = setup_result.stderr.strip()
            await resolved_manager.update_job(
                str(job.id),
                status="failed",
                exit_code=setup_result.exit_code,
                error_text=stderr or None,
            )
            raise SandboxCommandExecutionError(
                "Docker sandbox Python environment setup failed "
                f"(exit_code={setup_result.exit_code}, stderr={stderr or 'none'})",
                output={
                    "status": "failed",
                    "operation": "python_script",
                    "stdout": setup_result.stdout.strip(),
                    "stderr": stderr,
                    "exit_code": setup_result.exit_code,
                    "docker_image": runtime_image,
                    "sandbox_environment_id": str(environment.id),
                    "sandbox_job_id": str(job.id),
                    "script_path": script_path,
                    "script_name": safe_name,
                    "script_hash": script_hash,
                },
            )
        if normalized_dependency_hints:
            packages, install_job_id = await _install_dependencies(
                sandbox=sandbox,
                manager=resolved_manager,
                workspace_id=workspace_id,
                environment_id=str(environment.id),
                execution_id=execution_id,
                node_id=node_id,
                run_job_id=str(job.id),
                sandbox_policy=dict(sandbox_policy),
                resource_limits=dict(limits),
                runtime_image=runtime_image,
                packages=normalized_dependency_hints,
                reason="declared_hints",
                timeout=sandbox_timeout,
            )
            installed_packages.extend(packages)
            install_job_ids.append(install_job_id)
        await sandbox.write_file(script_path, script)
        result = await sandbox.execute_command(
            command,
            timeout=sandbox_timeout,
            network_profile="none",
        )
        missing_module = detect_missing_python_module("\n".join([result.stderr, result.stdout]))
        missing_package = (
            resolve_package_for_missing_module(missing_module, normalized_dependency_hints)
            if missing_module
            else None
        )
        if (
            not result.success
            and missing_package
            and _package_not_installed(missing_package, installed_packages)
        ):
            packages, install_job_id = await _install_dependencies(
                sandbox=sandbox,
                manager=resolved_manager,
                workspace_id=workspace_id,
                environment_id=str(environment.id),
                execution_id=execution_id,
                node_id=node_id,
                run_job_id=str(job.id),
                sandbox_policy=dict(sandbox_policy),
                resource_limits=dict(limits),
                runtime_image=runtime_image,
                packages=[missing_package],
                reason="missing_module_retry",
                timeout=sandbox_timeout,
            )
            installed_packages.extend(packages)
            install_job_ids.append(install_job_id)
            retry_count = 1
            result = await sandbox.execute_command(
                command,
                timeout=sandbox_timeout,
                network_profile="none",
            )
    except Exception as exc:
        await _mark_job_failed(
            resolved_manager,
            str(job.id),
            exit_code=_exception_exit_code_for_job(exc, str(job.id)),
            error_text=str(exc) or type(exc).__name__,
        )
        raise
    finally:
        if sandbox is not None:
            with suppress(Exception):
                await resolved_provider.release(sandbox)
        if lease_token is not None:
            with suppress(Exception):
                await resolved_manager.release_lease(
                    workspace_id=workspace_id,
                    lease_token=lease_token,
                )

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    parsed_stdout: dict[str, Any] = {}
    if stdout:
        try:
            loaded = json.loads(stdout)
            parsed_stdout = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            parsed_stdout = {}

    report_markdown = (
        "# Sandbox Python 执行报告\n\n"
        "- 执行位置：LeadAgentRuntime / subagent node\n"
        "- 隔离方式：Docker sandbox\n"
        f"- Workspace：{workspace_id}\n"
        f"- Execution：{execution_id}\n"
        f"- Node：{node_id}\n"
        f"- Script：{safe_name}\n"
        f"- Script SHA256：`{script_hash}`\n"
        f"- Docker image：{getattr(resolved_provider, 'image', None)}\n"
        f"- Exit code：{result.exit_code}\n\n"
        "## stdout\n\n"
        "```text\n"
        f"{stdout}\n"
        "```\n\n"
        "## stderr\n\n"
        "```text\n"
        f"{stderr}\n"
        "```\n"
    )
    output = {
        "status": "completed",
        "operation": "python_script",
        "stdout": stdout,
        "stderr": stderr,
        "parsed_stdout": parsed_stdout,
        "exit_code": result.exit_code,
        "docker_image": runtime_image,
        "sandbox_environment_id": str(environment.id),
        "sandbox_job_id": str(job.id),
        "dependency_hints": normalized_dependency_hints,
        "installed_packages": installed_packages,
        "install_job_ids": install_job_ids,
        "retry_count": retry_count,
        "script_path": script_path,
        "script_name": safe_name,
        "script_hash": script_hash,
        "report_markdown": report_markdown,
    }
    if not result.success:
        output["status"] = "failed"
        await resolved_manager.update_job(
            str(job.id),
            status="failed",
            exit_code=result.exit_code,
            error_text=stderr or None,
        )
        raise SandboxCommandExecutionError(
            "Docker sandbox Python script failed "
            f"(exit_code={result.exit_code}, stderr={stderr or 'none'})",
            output=output,
        )

    await resolved_manager.update_job(str(job.id), status="succeeded", exit_code=result.exit_code)
    return output


def _safe_script_name(value: str) -> str:
    name = _SCRIPT_NAME_RE.sub("_", str(value or "").strip())
    if not name or name in {".", ".."}:
        name = "analysis.py"
    if not name.endswith(".py"):
        name = f"{name}.py"
    return name[:80]


def _package_not_installed(package_spec: str, installed_packages: list[str]) -> bool:
    normalized = normalize_dependency_hints([package_spec])[0].lower().replace("_", "-")
    installed = {item.lower().replace("_", "-") for item in installed_packages}
    return normalized not in installed
