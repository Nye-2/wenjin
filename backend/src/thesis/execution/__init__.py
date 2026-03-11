# src/thesis/execution/__init__.py
"""Execution tools for thesis workflow.

This module provides tool wrappers around ExecutionService
for use by thesis workflow nodes.
"""

from typing import Any

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
]

# Global execution service instance (lazy initialization)
_execution_service: Any = None


def get_execution_service() -> Any:
    """Get the global ExecutionService instance.

    In production, this should be injected via dependency injection.
    For now, creates a new DockerExecutionService on first call.

    Returns:
        ExecutionService instance
    """
    global _execution_service
    if _execution_service is None:
        from src.execution.service import DockerExecutionService
        import os
        sandbox_dir = os.environ.get("SANDBOX_DIR", "/tmp/academiagpt-sandbox")
        _execution_service = DockerExecutionService(sandbox_base_dir=sandbox_dir)
    return _execution_service


def set_execution_service(service: Any) -> None:
    """Set the global ExecutionService instance.

    Used for dependency injection, especially in tests.

    Args:
        service: ExecutionService instance to use globally
    """
    global _execution_service
    _execution_service = service
