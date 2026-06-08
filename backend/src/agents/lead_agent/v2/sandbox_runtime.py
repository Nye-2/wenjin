"""Lead-agent owned sandbox execution facade.

Only the right-side LeadAgentRuntime/subagent path should import this module.
The left chat agent may launch capabilities, but must not acquire or execute a
sandbox directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.agents.lead_agent.v2.sandbox_artifact_collector import SandboxArtifactCollector
from src.agents.lead_agent.v2.sandbox_environment_installer import SandboxEnvironmentInstaller
from src.agents.lead_agent.v2.sandbox_errors import SandboxCommandExecutionError
from src.agents.lead_agent.v2.sandbox_job_runner import SandboxJobRunner
from src.agents.lead_agent.v2.workspace_sandbox import WorkspaceSandboxManager
from src.sandbox.providers.docker import DockerSandboxProvider

__all__ = [
    "SandboxCommandExecutionError",
    "require_run_python_allowed",
    "run_python_script",
    "run_python_smoke_check",
]


def require_run_python_allowed(policy: Mapping[str, Any]) -> None:
    """Raise when the capability policy does not allow Python sandbox execution."""
    mode = str(policy.get("mode") or "none")
    allowed = {str(item) for item in policy.get("allowed_operations") or []}
    if mode not in {"required", "optional", "conditional"} or "run_python" not in allowed:
        raise PermissionError("capability sandbox_policy does not allow run_python")


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
    return await SandboxJobRunner(
        provider=provider,
        manager=manager,
        installer=SandboxEnvironmentInstaller(),
        collector=SandboxArtifactCollector(),
    ).run_smoke_check(
        workspace_id=workspace_id,
        execution_id=execution_id,
        node_id=node_id,
        sandbox_policy=sandbox_policy,
        billing_reservation_id=billing_reservation_id,
    )


async def run_python_script(
    *,
    workspace_id: str,
    execution_id: str,
    node_id: str,
    sandbox_policy: Mapping[str, Any],
    script: str,
    script_name: str = "analysis.py",
    dependency_hints: list[str] | str | None = None,
    dataset_provenance: list[dict[str, Any]] | None = None,
    provider: DockerSandboxProvider | None = None,
    manager: WorkspaceSandboxManager | None = None,
    billing_reservation_id: str | None = None,
) -> dict[str, Any]:
    """Run a capability-declared Python script in the Docker sandbox."""

    require_run_python_allowed(sandbox_policy)
    return await SandboxJobRunner(
        provider=provider,
        manager=manager,
        installer=SandboxEnvironmentInstaller(),
        collector=SandboxArtifactCollector(),
    ).run_python_script(
        workspace_id=workspace_id,
        execution_id=execution_id,
        node_id=node_id,
        sandbox_policy=sandbox_policy,
        script=script,
        script_name=script_name,
        dependency_hints=dependency_hints,
        dataset_provenance=dataset_provenance,
        billing_reservation_id=billing_reservation_id,
    )
