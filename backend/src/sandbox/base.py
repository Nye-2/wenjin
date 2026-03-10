"""Sandbox abstract base class and data classes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class CommandResult:
    """Result of command execution in sandbox.

    Attributes:
        stdout: Standard output from the command.
        stderr: Standard error from the command.
        exit_code: Exit code of the command (0 = success).
        timed_out: Whether the command timed out.
    """

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

    @property
    def success(self) -> bool:
        """Check if command executed successfully."""
        return self.exit_code == 0 and not self.timed_out


@dataclass
class FileInfo:
    """Information about a file or directory.

    Attributes:
        name: Name of the file or directory.
        path: Absolute path to the file or directory.
        is_dir: Whether this is a directory.
        size: File size in bytes (None for directories).
    """

    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None


class Sandbox(ABC):
    """Abstract base class for sandbox environments.

    A sandbox provides isolated execution environment with:
    - Command execution
    - File system operations
    - Path isolation
    """

    def __init__(self, id: str):
        """Initialize sandbox with unique identifier.

        Args:
            id: Unique sandbox identifier (e.g., thread_id).
        """
        self._id = id

    @property
    def sandbox_id(self) -> str:
        """Get sandbox identifier."""
        return self._id

    @abstractmethod
    async def execute_command(
        self,
        command: str,
        timeout: int = 300,
    ) -> CommandResult:
        """Execute a shell command in the sandbox.

        Args:
            command: Shell command to execute.
            timeout: Maximum execution time in seconds.

        Returns:
            CommandResult with stdout, stderr, and exit code.
        """
        pass

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Read file contents.

        Args:
            path: Absolute path to the file.

        Returns:
            File contents as string.
        """
        pass

    @abstractmethod
    async def write_file(
        self,
        path: str,
        content: str,
        append: bool = False,
    ) -> None:
        """Write content to a file.

        Args:
            path: Absolute path to the file.
            content: Content to write.
            append: Whether to append to existing file.
        """
        pass

    @abstractmethod
    async def list_dir(self, path: str, max_depth: int = 2) -> list[FileInfo]:
        """List directory contents.

        Args:
            path: Absolute path to directory.
            max_depth: Maximum depth to traverse.

        Returns:
            List of FileInfo for directory contents.
        """
        pass
