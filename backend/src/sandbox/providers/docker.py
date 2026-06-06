"""Docker-backed sandbox provider."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from src.execution.docker.client import (
    SANDBOX_KIND_LABEL,
    SANDBOX_MANAGED_LABEL,
    SANDBOX_THREAD_LABEL,
    DockerClient,
    DockerExecutionError,
)
from src.sandbox.base import CommandResult, Sandbox
from src.sandbox.providers.base import SandboxProvider
from src.sandbox.providers.local import LocalSandbox, SandboxSecurityError
from src.sandbox.workspace_layout import WORKSPACE_ROOT, ensure_workspace_sandbox_layout

logger = logging.getLogger(__name__)


class DockerSandbox(LocalSandbox):
    """Sandbox that executes shell commands inside ephemeral Docker containers."""

    _CONTAINER_WORKSPACE_ROOT = WORKSPACE_ROOT
    _CONTAINER_KIND = "sandbox_exec"
    _NETWORK_PROFILES = frozenset({"none", "restricted_egress", "package_index_only"})

    def __init__(
        self,
        *,
        id: str,
        path_mappings: dict[str, str],
        image: str,
        docker_client: DockerClient,
        memory: str,
        cpu_limit: int,
    ) -> None:
        super().__init__(id=id, path_mappings=path_mappings)
        self._image = image
        self._docker_client = docker_client
        self._memory = memory
        self._cpu_limit = cpu_limit

    def _host_workspace_root(self) -> str:
        return str(Path(self.path_mappings["/workspace"]).resolve())

    async def execute_command(
        self,
        command: str,
        timeout: int = 300,
        *,
        network_profile: str = "none",
    ) -> CommandResult:
        if network_profile not in self._NETWORK_PROFILES:
            return CommandResult(
                stdout="",
                stderr=f"Unsupported sandbox network profile: {network_profile}",
                exit_code=1,
            )
        try:
            self._validate_command(command)
        except SandboxSecurityError as exc:
            return CommandResult(stdout="", stderr=str(exc), exit_code=1)

        network_disabled = network_profile == "none"
        try:
            exit_code, stdout, stderr = await self._docker_client.run_container(
                image=self._image,
                command=["/bin/sh", "-lc", command],
                volumes=self._docker_client.build_volume_mapping(
                    self._host_workspace_root(),
                    self._CONTAINER_WORKSPACE_ROOT,
                ),
                working_dir=self._CONTAINER_WORKSPACE_ROOT,
                timeout=timeout,
                remove=True,
                network_disabled=network_disabled,
                mem_limit=self._memory,
                nano_cpus=int(self._cpu_limit * 1_000_000_000),
                labels={
                    SANDBOX_MANAGED_LABEL: "true",
                    SANDBOX_KIND_LABEL: self._CONTAINER_KIND,
                    SANDBOX_THREAD_LABEL: self.sandbox_id,
                    "wenjin.sandbox.network_profile": network_profile,
                },
            )
            return CommandResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                timed_out=False,
            )
        except TimeoutError:
            return CommandResult(
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                timed_out=True,
            )
        except DockerExecutionError as exc:
            return CommandResult(stdout="", stderr=str(exc), exit_code=1)
        except Exception as exc:
            logger.exception("Docker sandbox command failed")
            return CommandResult(stdout="", stderr=str(exc), exit_code=1)


class DockerSandboxProvider(SandboxProvider):
    """Provider for DockerSandbox instances."""

    def __init__(
        self,
        *,
        base_dir: str,
        image: str,
        timeout: int = 300,
        memory: str = "1g",
        cpu_limit: int = 2,
        cleanup_on_release: bool = False,
        docker_client: DockerClient | None = None,
    ) -> None:
        self.base_dir = str(Path(base_dir).resolve())
        self.image = image
        self.timeout = timeout
        self.memory = memory
        self.cpu_limit = cpu_limit
        self._cleanup_on_release = cleanup_on_release
        self._docker_client = docker_client or DockerClient()
        self._sandboxes: dict[str, DockerSandbox] = {}
        self._lock = asyncio.Lock()
        self._reconciled = False

    async def _reconcile_orphaned_exec_containers(self) -> None:
        if self._reconciled:
            return

        labels = {
            SANDBOX_MANAGED_LABEL: "true",
            SANDBOX_KIND_LABEL: DockerSandbox._CONTAINER_KIND,
        }
        try:
            removed = await self._docker_client.cleanup_containers_by_label(labels)
            if removed:
                logger.info("Reconciled %d orphaned sandbox execution container(s)", removed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to reconcile orphaned sandbox containers: %s", exc)
        finally:
            self._reconciled = True

    async def acquire(self, thread_id: str) -> DockerSandbox:
        async with self._lock:
            if thread_id in self._sandboxes:
                return self._sandboxes[thread_id]

            await self._reconcile_orphaned_exec_containers()

            workspace_path = Path(self.base_dir) / thread_id / "workspace"
            ensure_workspace_sandbox_layout(
                workspace_path,
                sandbox_id=thread_id,
                workspace_id=thread_id.removeprefix("workspace-"),
            )

            await self._docker_client.ensure_image(self.image)

            path_mappings = {
                "/workspace": str(workspace_path),
            }
            sandbox = DockerSandbox(
                id=thread_id,
                path_mappings=path_mappings,
                image=self.image,
                docker_client=self._docker_client,
                memory=self.memory,
                cpu_limit=self.cpu_limit,
            )
            self._sandboxes[thread_id] = sandbox
            return sandbox

    def get(self, sandbox_id: str) -> DockerSandbox | None:
        return self._sandboxes.get(sandbox_id)

    async def release(self, sandbox: Sandbox) -> None:
        async with self._lock:
            sandbox_id = sandbox.sandbox_id
            if sandbox_id not in self._sandboxes:
                return

            del self._sandboxes[sandbox_id]

            if self._cleanup_on_release:
                thread_path = Path(self.base_dir) / sandbox_id
                if thread_path.exists():
                    try:
                        shutil.rmtree(thread_path)
                    except OSError:
                        logger.warning("Failed to cleanup docker sandbox %s", sandbox_id, exc_info=True)
