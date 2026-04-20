"""Execution tools package."""

from .compile_latex import compile_latex, compile_latex_tool

__all__ = ["compile_latex_tool", "compile_latex"]


def get_execution_tools() -> list:
    """Get all execution tool instances.

    Returns:
        List of execution tool instances.
    """
    return [compile_latex_tool]
