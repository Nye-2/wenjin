"""Runtime context and lease management for lead-agent sandbox jobs."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agents.lead_agent.v2.sandbox_errors import SandboxCommandExecutionError
from src.agents.lead_agent.v2.workspace_sandbox import WorkspaceSandboxManager, workspace_provider_key
from src.sandbox.providers.docker import DockerSandboxProvider
from src.sandbox.workspace_layout import WORKSPACE_ROOT, ensure_workspace_sandbox_layout


@dataclass(frozen=True)
class SandboxRuntimeContext:
    """Resolved sandbox environment context for one job."""

    limits: Mapping[str, Any]
    sandbox_timeout: int
    provider: Any
    runtime_image: str
    manager: WorkspaceSandboxManager
    environment: Any
    sandbox_key: str
    workspace_type: str | None = None


class SandboxRuntimeSession:
    """Resolve provider/manager state and own lease acquire/release."""

    def __init__(
        self,
        *,
        provider: DockerSandboxProvider | None = None,
        manager: WorkspaceSandboxManager | None = None,
    ) -> None:
        self.provider = provider
        self.manager = manager

    async def build_context(
        self,
        *,
        workspace_id: str,
        sandbox_policy: Mapping[str, Any],
        workspace_type: str | None = None,
    ) -> SandboxRuntimeContext:
        limits = resource_limits(sandbox_policy)
        provider = self.provider or provider_from_policy(sandbox_policy)
        runtime_image = provider_image(provider) or default_image()
        manager = self.manager or WorkspaceSandboxManager()
        environment = await manager.get_or_create_environment(
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            sandbox_policy=dict(sandbox_policy),
            resource_limits=dict(limits),
            runtime_image=runtime_image,
        )
        return SandboxRuntimeContext(
            limits=limits,
            sandbox_timeout=sandbox_timeout(limits),
            provider=provider,
            runtime_image=runtime_image,
            manager=manager,
            environment=environment,
            sandbox_key=environment_provider_key(environment, workspace_id),
            workspace_type=str(workspace_type or "").strip() or None,
        )

    @asynccontextmanager
    async def leased_sandbox(
        self,
        *,
        ctx: SandboxRuntimeContext,
        workspace_id: str,
        execution_id: str,
        job_id: str,
    ) -> AsyncIterator[Any]:
        lease_token: str | None = None
        sandbox = None
        try:
            lease_token = await ctx.manager.acquire_lease(
                workspace_id=workspace_id,
                environment_id=str(ctx.environment.id),
                job_id=job_id,
                execution_id=execution_id,
                ttl_seconds=max(ctx.sandbox_timeout + 60, 120),
            )
            sandbox = await ctx.provider.acquire(ctx.sandbox_key)
            ensure_runtime_workspace_layout(
                sandbox=sandbox,
                workspace_id=workspace_id,
                sandbox_id=ctx.sandbox_key,
                workspace_type=ctx.workspace_type,
            )
            await ctx.manager.update_job(job_id, status="running")
            yield sandbox
        finally:
            await release_runtime_resources(
                provider=ctx.provider,
                manager=ctx.manager,
                sandbox=sandbox,
                workspace_id=workspace_id,
                lease_token=lease_token,
            )


def default_base_dir() -> str:
    configured = os.getenv("WENJIN_AGENT_SANDBOX_BASE_DIR")
    if configured:
        return configured

    latex_dir = os.getenv("WENJIN_LATEX_DATA_DIR")
    if latex_dir:
        return str(Path(latex_dir).expanduser().resolve().parent / "agent_sandboxes")

    return str((Path.cwd() / ".wenjin" / "agent_sandboxes").resolve())


def default_image() -> str:
    return os.getenv(
        "WENJIN_AGENT_SANDBOX_IMAGE",
        "docker.m.daocloud.io/library/python:3.13-slim",
    )


def resource_limits(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    limits = policy.get("resource_limits")
    return limits if isinstance(limits, Mapping) else {}


def sandbox_timeout(limits: Mapping[str, Any]) -> int:
    timeout_seconds = int(limits.get("timeout_seconds") or 120)
    return max(1, min(timeout_seconds, 120))


def provider_from_policy(policy: Mapping[str, Any]) -> DockerSandboxProvider:
    limits = resource_limits(policy)
    memory_mb = int(limits.get("memory_mb") or os.getenv("WENJIN_AGENT_SANDBOX_MEMORY_MB") or 512)
    cpu_limit = int(limits.get("cpu") or os.getenv("WENJIN_AGENT_SANDBOX_CPU") or 1)
    timeout_seconds = int(limits.get("timeout_seconds") or 120)
    return DockerSandboxProvider(
        base_dir=default_base_dir(),
        image=default_image(),
        timeout=timeout_seconds,
        memory=f"{memory_mb}m",
        cpu_limit=cpu_limit,
    )


def provider_image(provider: Any) -> str | None:
    value = getattr(provider, "image", None)
    return str(value) if value else None


def environment_provider_key(environment: Any, workspace_id: str) -> str:
    return str(
        getattr(environment, "sandbox_id", None)
        or getattr(environment, "metadata_json", {}).get("provider_key")
        or workspace_provider_key(workspace_id)
    )


def ensure_runtime_workspace_layout(
    *,
    sandbox: Any,
    workspace_id: str,
    sandbox_id: str,
    workspace_type: str | None,
) -> None:
    """Refresh the mounted `/workspace` manifest with Lead-known workspace metadata."""

    workspace_root = runtime_workspace_physical_root(sandbox)
    if workspace_root is None:
        return
    ensure_workspace_sandbox_layout(
        workspace_root,
        workspace_id=workspace_id,
        sandbox_id=sandbox_id,
        workspace_type=workspace_type,
    )


def runtime_workspace_physical_root(sandbox: Any) -> Path | None:
    resolver = getattr(sandbox, "_resolve_path", None)
    if callable(resolver):
        try:
            return Path(resolver(WORKSPACE_ROOT))
        except Exception:  # noqa: BLE001 - provider-specific path mapping failures are ignored here.
            return None
    mappings = getattr(sandbox, "path_mappings", None)
    if isinstance(mappings, dict) and WORKSPACE_ROOT in mappings:
        return Path(str(mappings[WORKSPACE_ROOT]))
    return None


async def mark_job_failed(
    manager: Any,
    job_id: str,
    *,
    exit_code: int | None = None,
    error_text: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    with suppress(Exception):
        await manager.update_job(
            str(job_id),
            status="failed",
            exit_code=exit_code,
            error_text=error_text,
            metadata_json=metadata_json,
        )


def exception_exit_code_for_job(exc: Exception, job_id: str) -> int | None:
    if not isinstance(exc, SandboxCommandExecutionError):
        return None
    output = exc.output if isinstance(exc.output, dict) else {}
    if str(output.get("sandbox_job_id") or "") != str(job_id):
        return None
    try:
        return int(output.get("exit_code"))
    except (TypeError, ValueError):
        return None


async def release_runtime_resources(
    *,
    provider: Any,
    manager: Any,
    sandbox: Any,
    workspace_id: str,
    lease_token: str | None,
) -> None:
    if sandbox is not None:
        with suppress(Exception):
            await provider.release(sandbox)
    if lease_token is not None:
        with suppress(Exception):
            await manager.release_lease(
                workspace_id=workspace_id,
                lease_token=lease_token,
            )
