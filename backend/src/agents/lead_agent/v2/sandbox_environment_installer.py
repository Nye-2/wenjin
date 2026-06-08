"""Python environment setup and dependency installation for sandbox jobs."""

from __future__ import annotations

from typing import Any

from src.agents.harness.command_audit import (
    CommandAuditPolicy,
    HarnessCommand,
    audit_command,
    require_command_policy_allowed,
)
from src.agents.lead_agent.v2.sandbox_errors import SandboxCommandExecutionError
from src.agents.lead_agent.v2.workspace_sandbox import (
    ENSURE_WORKSPACE_VENV_COMMAND,
    build_pip_install_argv,
    build_pip_install_command,
    install_policy_snapshot,
    normalize_dependency_hints,
    policy_allows_package_install,
)
from src.sandbox.base import CommandResult, Sandbox


class SandboxEnvironmentInstaller:
    """Install the workspace Python runtime and declared dependencies."""

    async def ensure_python_environment(
        self,
        sandbox: Sandbox,
        *,
        timeout: int,
    ) -> CommandResult:
        return await sandbox.execute_command(
            ENSURE_WORKSPACE_VENV_COMMAND,
            timeout=timeout,
            network_profile="none",
        )

    async def install_dependencies(
        self,
        *,
        sandbox: Sandbox,
        manager: Any,
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
    ) -> tuple[list[str], str, dict[str, Any]]:
        if not policy_allows_package_install(sandbox_policy):
            raise PermissionError("capability sandbox_policy does not allow package installation")

        normalized_packages = normalize_dependency_hints(packages)
        command = build_pip_install_command(normalized_packages)
        command_audit_result = audit_command(
            HarnessCommand(
                argv=build_pip_install_argv(normalized_packages),
                network_profile="package_index_only",
            ),
            CommandAuditPolicy(
                allow_package_install=True,
                allowed_network_profiles=("none", "package_index_only"),
            ),
        )
        require_command_policy_allowed(command_audit_result)
        command_audit = command_audit_result.model_dump()
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
                "command_audit": command_audit,
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
        return normalized_packages, str(install_job.id), command_audit

    def package_not_installed(self, package_spec: str, installed_packages: list[str]) -> bool:
        normalized = normalize_dependency_hints([package_spec])[0].lower().replace("_", "-")
        installed = {item.lower().replace("_", "-") for item in installed_packages}
        return normalized not in installed
