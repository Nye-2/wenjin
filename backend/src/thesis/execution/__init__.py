# src/thesis/execution/__init__.py
"""Execution tools for thesis workflow.

This module provides tool wrappers around ExecutionService
for use by thesis workflow nodes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.execution.types import ExecutionRequest, ExecutionResult

# Forward declarations (will be implemented in separate modules)
# These imports will work once latex_tool.py and figure_tool.py are created
try:
    from .latex_tool import compile_latex, CompileLatexResult
    from .figure_tool import generate_figure, GenerateFigureResult
except ImportError:
    # Allow module to load before submodules are created
    compile_latex = None  # type: ignore
    CompileLatexResult = None  # type: ignore
    generate_figure = None  # type: ignore
    GenerateFigureResult = None  # type: ignore

__all__ = [
    "compile_latex",
    "CompileLatexResult",
    "generate_figure",
    "GenerateFigureResult",
    "get_execution_service",
    "set_execution_service",
    "ExecutionServiceProtocol",
]


class ExecutionServiceProtocol(Protocol):
    """Protocol defining ExecutionService interface.

    Use this for type hints instead of `Any` to get proper
    IDE support and type checking.
    """

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a task.

        Args:
            request: Execution request with type, content, and options.

        Returns:
            ExecutionResult with status and output path.
        """
        ...

    async def health_check(self) -> dict:
        """Check service health.

        Returns:
            Health status dictionary.
        """
        ...


# Global execution service instance (lazy initialization)
_execution_service: ExecutionServiceProtocol | None = None


def get_execution_service() -> ExecutionServiceProtocol:
    """Get the global ExecutionService instance.

    In production, this should be injected via dependency injection.
    For now, creates a new DockerExecutionService on first call.

    Returns:
        ExecutionService instance

    Raises:
        RuntimeError: If ExecutionService fails to initialize
    """
    global _execution_service
    if _execution_service is None:
        try:
            import os

            from src.execution.public_paths import get_default_sandbox_dir
            from src.execution.service import DockerExecutionService

            sandbox_dir = os.environ.get("SANDBOX_DIR") or get_default_sandbox_dir()
            _execution_service = DockerExecutionService(sandbox_base_dir=sandbox_dir)
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize ExecutionService: {e}. "
                "Call set_execution_service() to inject a mock for testing."
            ) from e
    return _execution_service


def set_execution_service(service: ExecutionServiceProtocol | None) -> None:
    """Set the global ExecutionService instance.

    Used for dependency injection, especially in tests.

    Args:
        service: ExecutionService instance to use globally
    """
    global _execution_service
    _execution_service = service
