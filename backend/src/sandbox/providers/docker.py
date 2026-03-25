"""Docker-backed sandbox provider."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from src.execution.docker.client import DockerClient, DockerExecutionError
from src.sandbox.base import CommandResult, Sandbox
from src.sandbox.providers.base import SandboxProvider
from src.sandbox.providers.local import LocalSandbox, LocalSandboxProvider, SandboxSecurityError

logger = logging.getLogger(__name__)


class DockerSandbox(LocalSandbox):
    """Sandbox that executes shell commands inside ephemeral Docker containers."""

    _CONTAINER_USER_DATA_ROOT = "/mnt/user-data"
    _CONTAINER_WORKSPACE_ROOT = f"{_CONTAINER_USER_DATA_ROOT}/workspace"

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

    def _host_user_data_root(self) -> str:
        workspace_path = self.path_mappings["/mnt/user-data/workspace"]
        return str(Path(workspace_path).resolve().parent)

    async def execute_command(
        self,
        command: str,
        timeout: int = 300,
    ) -> CommandResult:
        try:
            self._validate_command(command)
        except SandboxSecurityError as exc:
            return CommandResult(stdout="", stderr=str(exc), exit_code=1)

        try:
            exit_code, stdout, stderr = await self._docker_client.run_container(
                image=self._image,
                command=["/bin/sh", "-lc", command],
                volumes=self._docker_client.build_volume_mapping(
                    self._host_user_data_root(),
                    self._CONTAINER_USER_DATA_ROOT,
                ),
                working_dir=self._CONTAINER_WORKSPACE_ROOT,
                timeout=timeout,
                remove=True,
                network_disabled=True,
                mem_limit=self._memory,
                nano_cpus=int(self._cpu_limit * 1_000_000_000),
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

    async def acquire(self, thread_id: str) -> DockerSandbox:
        async with self._lock:
            if thread_id in self._sandboxes:
                return self._sandboxes[thread_id]

            user_data_path = LocalSandboxProvider._get_user_data_root(self.base_dir, thread_id)
            for subdir in ("workspace", "uploads", "outputs"):
                (user_data_path / subdir).mkdir(parents=True, exist_ok=True)

            await self._docker_client.ensure_image(self.image)

            path_mappings = {
                f"/mnt/user-data/{subdir}": str(user_data_path / subdir)
                for subdir in ("workspace", "uploads", "outputs")
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
