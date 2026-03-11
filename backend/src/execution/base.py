"""Abstract base classes for execution service."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import ExecutionRequest, ExecutionResult, ProviderResult


class ExecutionService(ABC):
    """Abstract execution service interface.

    Allows future migration to microservices architecture.
    """

    @abstractmethod
    async def execute(self, request: "ExecutionRequest") -> "ExecutionResult":
        """Execute a task.

        Args:
            request: Execution request with type, content, and options.

        Returns:
            ExecutionResult with status and output path.
        """
        pass

    @abstractmethod
    async def health_check(self) -> dict:
        """Check service health.

        Returns:
            Health status dictionary.
        """
        pass


class ExecutionProvider(ABC):
    """Abstract execution provider.

    Each provider handles a specific execution type.
    """

    @property
    @abstractmethod
    def execution_type(self) -> str:
        """Execution type this provider handles."""
        pass

    @property
    @abstractmethod
    def docker_image(self) -> str | None:
        """Docker image name, or None if no Docker needed."""
        pass

    def build_command(self, content: str, options: dict) -> list[str]:
        """Build Docker command for execution.

        Args:
            content: Source code or prompt.
            options: Execution options.

        Returns:
            Command list for Docker execution.
        """
        return []

    @abstractmethod
    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict,
        docker_client: object | None = None,
    ) -> "ProviderResult":
        """Execute the task.

        Args:
            content: Source code or prompt.
            work_dir: Working directory path.
            options: Execution options.
            docker_client: Optional Docker client.

        Returns:
            ProviderResult with output files and metadata.
        """
        pass

    async def process_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        work_dir: str,
        options: dict,
    ) -> "ProviderResult":
        """Process Docker execution result.

        Override this if using Docker execution.

        Args:
            exit_code: Container exit code.
            stdout: Container stdout.
            stderr: Container stderr.
            work_dir: Working directory path.
            options: Execution options.

        Returns:
            ProviderResult with output files.
        """
        raise NotImplementedError("Override for Docker-based providers")
