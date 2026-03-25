"""Local sandbox implementation using host filesystem."""

import asyncio
import logging
import os
import re
import shlex
import shutil
from pathlib import Path

from src.sandbox.base import CommandResult, FileInfo, Sandbox
from src.sandbox.providers.base import SandboxProvider

logger = logging.getLogger(__name__)


class SandboxSecurityError(PermissionError):
    """Raised when a security violation is detected."""

    pass


class LocalSandbox(Sandbox):
    """Sandbox implementation using local filesystem.

    Uses path mappings to translate virtual paths to physical paths.
    Commands are executed directly on the host system.

    Security:
        - Only paths under /mnt/user-data/* are accessible
        - Path traversal attempts (..) are blocked
        - Symbolic links are resolved and validated
    """

    # Allowed virtual path prefixes
    ALLOWED_VIRTUAL_PREFIXES = frozenset(["/mnt/user-data"])
    _COMMAND_ABSOLUTE_PATH_RE = re.compile(
        r"(?<![A-Za-z0-9_.:/])(\/(?!\/)[^ \t\r\n'\"`|&;<>(),]*)"
    )
    _COMMAND_RELATIVE_TRAVERSAL_RE = re.compile(
        r"(?<![A-Za-z0-9_])((?:\./)*(?:\.\./)+[^ \t\r\n'\"`|&;<>(),]*|\.\.(?=$|[ \t\r\n'\"`|&;<>(),]))"
    )
    _COMMAND_HOME_PATH_RE = re.compile(
        r"(?<![A-Za-z0-9_])(~(?:\/[^ \t\r\n'\"`|&;<>(),]*)?)"
    )

    def __init__(self, id: str, path_mappings: dict[str, str]):
        """Initialize local sandbox.

        Args:
            id: Sandbox identifier (usually thread_id).
            path_mappings: Dict mapping virtual paths to physical paths.
        """
        super().__init__(id)
        self.path_mappings = path_mappings
        # Cache resolved base paths for security checks
        self._resolved_base_paths = {
            vp: str(Path(pp).resolve()) for vp, pp in path_mappings.items()
        }
        self._workspace_path = path_mappings.get("/mnt/user-data/workspace")

    @staticmethod
    def _is_within_root(path: str, root: str) -> bool:
        """Return whether a resolved path stays under a resolved root."""
        try:
            return os.path.commonpath([path, root]) == root
        except ValueError:
            return False

    def _is_within_allowed_roots(self, path: str) -> bool:
        """Return whether a physical path remains inside any mapped sandbox root."""
        resolved = str(Path(path).resolve())
        return any(
            self._is_within_root(resolved, root)
            for root in self._resolved_base_paths.values()
        )

    def _resolve_path(self, path: str) -> str:
        """Resolve virtual path to physical path with security checks.

        Args:
            path: Virtual path to resolve.

        Returns:
            Resolved physical path.

        Raises:
            SandboxSecurityError: If path is outside sandbox or contains traversal.
        """
        path_str = str(path).strip()

        # Security: Check for null bytes
        if "\x00" in path_str:
            raise SandboxSecurityError(f"Null byte in path: {path}")

        # Security: Reject paths outside virtual namespace
        is_virtual_path = any(
            path_str.startswith(prefix) for prefix in self.ALLOWED_VIRTUAL_PREFIXES
        )
        if path_str.startswith("/") and not is_virtual_path:
            logger.warning(f"Access denied to non-virtual path: {path}")
            raise SandboxSecurityError(
                f"Access denied: path outside sandbox: {path}"
            )

        # Try each mapping (longest prefix first)
        for virtual_path, physical_path in sorted(
            self.path_mappings.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        ):
            if path_str.startswith(virtual_path):
                relative = path_str[len(virtual_path):].lstrip("/")

                # Security: Check for path traversal
                if ".." in relative or ".." in path_str:
                    raise SandboxSecurityError(
                        f"Path traversal detected: {path}"
                    )

                if relative:
                    resolved = str(Path(physical_path) / relative)
                else:
                    resolved = physical_path

                # Security: Verify resolved path is within allowed directory
                try:
                    real_resolved = str(Path(resolved).resolve())
                    real_base = self._resolved_base_paths[virtual_path]
                    if not self._is_within_root(real_resolved, real_base):
                        raise SandboxSecurityError(
                            f"Path escape detected: {path}"
                        )
                except (OSError, ValueError) as e:
                    raise SandboxSecurityError(
                        f"Cannot resolve path safely: {path}"
                    ) from e

                logger.debug(f"Resolved path: {path} -> {resolved}")
                return resolved

        # Non-absolute paths are allowed (relative to current directory)
        if not path_str.startswith("/"):
            return path_str

        raise SandboxSecurityError(f"Cannot resolve path: {path}")

    def _reverse_resolve_path(self, path: str) -> str:
        """Resolve physical path back to virtual path."""
        resolved = str(Path(path).resolve())

        for virtual_path, physical_path in sorted(
            self.path_mappings.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            physical_resolved = str(Path(physical_path).resolve())
            if self._is_within_root(resolved, physical_resolved):
                relative = resolved[len(physical_resolved):].lstrip("/")
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

    def _validate_relative_command_path(self, fragment: str) -> None:
        """Validate a relative path fragment against sandbox roots."""
        if self._workspace_path is None:
            raise SandboxSecurityError("Sandbox workspace is not configured.")

        resolved = str((Path(self._workspace_path) / fragment).resolve())
        if not self._is_within_allowed_roots(resolved):
            raise SandboxSecurityError(
                f"Command references path outside sandbox: {fragment}"
            )

    def _validate_command(self, command: str) -> None:
        """Reject path references that escape the sandbox roots."""
        if "\x00" in command:
            raise SandboxSecurityError("Command contains null byte.")

        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            tokens = [command]

        for token in tokens:
            for match in self._COMMAND_HOME_PATH_RE.finditer(token):
                raise SandboxSecurityError(
                    f"Command references unsupported home path: {match.group(1)}"
                )

            for match in self._COMMAND_ABSOLUTE_PATH_RE.finditer(token):
                fragment = match.group(1)
                if not fragment.startswith("/mnt/user-data"):
                    raise SandboxSecurityError(
                        f"Command references path outside sandbox: {fragment}"
                    )

            for match in self._COMMAND_RELATIVE_TRAVERSAL_RE.finditer(token):
                self._validate_relative_command_path(match.group(1))

    async def execute_command(
        self,
        command: str,
        timeout: int = 300,
    ) -> CommandResult:
        """Execute shell command."""
        try:
            self._validate_command(command)
        except SandboxSecurityError as exc:
            return CommandResult(
                stdout="",
                stderr=str(exc),
                exit_code=1,
            )

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
                cwd=self._workspace_path,
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

            except TimeoutError:
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
            with open(resolved, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}") from None
        except OSError as e:
            raise type(e)(e.errno, e.strerror, path) from e

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
            raise type(e)(e.errno, e.strerror, path) from e

    async def list_dir(
        self, path: str, max_depth: int = 2, _current_depth: int = 0
    ) -> list[FileInfo]:
        """List directory contents with optional depth limit.

        Args:
            path: Directory path to list (virtual or physical for internal recursion).
            max_depth: Maximum depth to traverse (0 = only current dir).
            _current_depth: Internal use for recursion.

        Returns:
            List of FileInfo for directory contents.
        """
        # For recursion, path might already be physical
        # Check if it's a virtual path or already resolved
        if path.startswith("/mnt/user-data"):
            resolved = self._resolve_path(path)
        else:
            # Already a physical path from recursion
            resolved = path

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

                # Recursively list subdirectories if within depth limit
                if is_dir and _current_depth < max_depth:
                    # Pass physical path for internal recursion
                    subentries = await self.list_dir(
                        entry_path,
                        max_depth=max_depth,
                        _current_depth=_current_depth + 1,
                    )
                    entries.extend(subentries)

        except PermissionError:
            raise PermissionError(f"Permission denied: {path}") from None

        return entries


class LocalSandboxProvider(SandboxProvider):
    """Provider for LocalSandbox instances.

    Manages sandbox lifecycle with thread-isolated directories.
    """

    def __init__(self, base_dir: str, cleanup_on_release: bool = False):
        """Initialize provider.

        Args:
            base_dir: Base directory for thread data.
            cleanup_on_release: If True, delete thread directory on release.
        """
        self.base_dir = str(Path(base_dir).resolve())
        self._sandboxes: dict[str, LocalSandbox] = {}
        self._lock = asyncio.Lock()
        self._cleanup_on_release = cleanup_on_release

    @staticmethod
    def _get_user_data_root(base_dir: str, thread_id: str) -> Path:
        """Resolve the persistent per-thread user-data directory."""
        return Path(base_dir) / thread_id / "user-data"

    async def acquire(self, thread_id: str) -> LocalSandbox:
        """Acquire or create sandbox for thread."""
        async with self._lock:
            if thread_id in self._sandboxes:
                return self._sandboxes[thread_id]

            # Create thread directories
            user_data_path = self._get_user_data_root(self.base_dir, thread_id)
            for subdir in ["workspace", "uploads", "outputs"]:
                (user_data_path / subdir).mkdir(parents=True, exist_ok=True)

            # Create path mappings
            path_mappings = {
                f"/mnt/user-data/{subdir}": str(user_data_path / subdir)
                for subdir in ["workspace", "uploads", "outputs"]
            }

            sandbox = LocalSandbox(id=thread_id, path_mappings=path_mappings)
            self._sandboxes[thread_id] = sandbox
            logger.info(f"Created sandbox for thread: {thread_id}")
            return sandbox

    def get(self, sandbox_id: str) -> LocalSandbox | None:
        """Get existing sandbox."""
        return self._sandboxes.get(sandbox_id)

    async def release(self, sandbox: Sandbox, cleanup: bool | None = None) -> None:
        """Release sandbox resources.

        Args:
            sandbox: Sandbox to release.
            cleanup: Override cleanup behavior. If None, uses instance default.
        """
        async with self._lock:
            sandbox_id = sandbox.sandbox_id
            if sandbox_id not in self._sandboxes:
                return

            del self._sandboxes[sandbox_id]

            # Optionally clean up physical resources
            should_cleanup = cleanup if cleanup is not None else self._cleanup_on_release
            if should_cleanup:
                thread_path = Path(self.base_dir) / sandbox_id
                if thread_path.exists():
                    try:
                        shutil.rmtree(thread_path)
                        logger.info(f"Cleaned up sandbox directory: {sandbox_id}")
                    except OSError as e:
                        logger.warning(f"Failed to cleanup sandbox {sandbox_id}: {e}")
