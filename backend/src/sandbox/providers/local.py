"""Local sandbox implementation using host filesystem."""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Optional

from src.sandbox.base import CommandResult, FileInfo, Sandbox
from src.sandbox.providers.base import SandboxProvider


class LocalSandbox(Sandbox):
    """Sandbox implementation using local filesystem.

    Uses path mappings to translate virtual paths to physical paths.
    Commands are executed directly on the host system.
    """

    def __init__(self, id: str, path_mappings: dict[str, str]):
        """Initialize local sandbox.

        Args:
            id: Sandbox identifier (usually thread_id).
            path_mappings: Dict mapping virtual paths to physical paths.
        """
        super().__init__(id)
        self.path_mappings = path_mappings

    def _resolve_path(self, path: str) -> str:
        """Resolve virtual path to physical path."""
        path_str = str(path)

        # Try each mapping (longest prefix first)
        for virtual_path, physical_path in sorted(
            self.path_mappings.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        ):
            if path_str.startswith(virtual_path):
                relative = path_str[len(virtual_path) :].lstrip("/")
                if relative:
                    return str(Path(physical_path) / relative)
                return physical_path

        return path_str

    def _reverse_resolve_path(self, path: str) -> str:
        """Resolve physical path back to virtual path."""
        resolved = str(Path(path).resolve())

        for virtual_path, physical_path in sorted(
            self.path_mappings.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            physical_resolved = str(Path(physical_path).resolve())
            if resolved.startswith(physical_resolved):
                relative = resolved[len(physical_resolved) :].lstrip("/")
                if relative:
                    return f"{virtual_path}/{relative}"
                return virtual_path

        return path

    @staticmethod
    def _get_shell() -> str:
        """Detect available shell."""
        for shell in ("/bin/zsh", "/bin/bash", "/bin/sh"):
            if os.path.isfile(shell) and os.access(shell, os.X_OK):
                return shell
        shell_from_path = shutil.which("sh")
        if shell_from_path:
            return shell_from_path
        return "/bin/sh"

    async def execute_command(
        self,
        command: str,
        timeout: int = 300,
    ) -> CommandResult:
        """Execute shell command."""
        # Resolve virtual paths in command
        resolved_command = command
        for virtual_path, physical_path in sorted(
            self.path_mappings.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        ):
            if virtual_path in resolved_command:
                resolved_command = resolved_command.replace(
                    virtual_path,
                    physical_path,
                )

        try:
            process = await asyncio.create_subprocess_shell(
                resolved_command,
                executable=self._get_shell(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )

                return CommandResult(
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    exit_code=process.returncode or 0,
                    timed_out=False,
                )

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return CommandResult(
                    stdout="",
                    stderr=f"Command timed out after {timeout} seconds",
                    exit_code=-1,
                    timed_out=True,
                )

        except Exception as e:
            return CommandResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
            )

    async def read_file(self, path: str) -> str:
        """Read file contents."""
        resolved = self._resolve_path(path)
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}")
        except OSError as e:
            raise type(e)(e.errno, e.strerror, path) from None

    async def write_file(
        self,
        path: str,
        content: str,
        append: bool = False,
    ) -> None:
        """Write content to file."""
        resolved = self._resolve_path(path)

        # Create parent directories
        dir_path = os.path.dirname(resolved)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        mode = "a" if append else "w"
        try:
            with open(resolved, mode, encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            raise type(e)(e.errno, e.strerror, path) from None

    async def list_dir(self, path: str, max_depth: int = 2) -> list[FileInfo]:
        """List directory contents."""
        resolved = self._resolve_path(path)

        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Directory not found: {path}")

        if not os.path.isdir(resolved):
            raise NotADirectoryError(f"Not a directory: {path}")

        entries = []
        try:
            for entry in sorted(os.listdir(resolved)):
                entry_path = os.path.join(resolved, entry)
                is_dir = os.path.isdir(entry_path)
                size = None if is_dir else os.path.getsize(entry_path)

                entries.append(FileInfo(
                    name=entry,
                    path=self._reverse_resolve_path(entry_path),
                    is_dir=is_dir,
                    size=size,
                ))
        except PermissionError:
            raise PermissionError(f"Permission denied: {path}")

        return entries


class LocalSandboxProvider(SandboxProvider):
    """Provider for LocalSandbox instances.

    Manages sandbox lifecycle with thread-isolated directories.
    """

    def __init__(self, base_dir: str):
        """Initialize provider.

        Args:
            base_dir: Base directory for thread data.
        """
        self.base_dir = str(Path(base_dir).resolve())
        self._sandboxes: dict[str, LocalSandbox] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, thread_id: str) -> LocalSandbox:
        """Acquire or create sandbox for thread."""
        async with self._lock:
            if thread_id in self._sandboxes:
                return self._sandboxes[thread_id]

            # Create thread directories
            thread_path = Path(self.base_dir) / thread_id
            for subdir in ["workspace", "uploads", "outputs"]:
                (thread_path / subdir).mkdir(parents=True, exist_ok=True)

            # Create path mappings
            path_mappings = {
                f"/mnt/user-data/{subdir}": str(thread_path / subdir)
                for subdir in ["workspace", "uploads", "outputs"]
            }

            sandbox = LocalSandbox(id=thread_id, path_mappings=path_mappings)
            self._sandboxes[thread_id] = sandbox
            return sandbox

    def get(self, sandbox_id: str) -> Optional[LocalSandbox]:
        """Get existing sandbox."""
        return self._sandboxes.get(sandbox_id)

    async def release(self, sandbox: Sandbox) -> None:
        """Release sandbox resources."""
        async with self._lock:
            if sandbox.sandbox_id in self._sandboxes:
                del self._sandboxes[sandbox.sandbox_id]
