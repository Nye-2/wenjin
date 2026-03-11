"""Execution service for LaTeX, Python, diagram, and AI image generation."""

from .types import (
    CompilerType,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    ImageProvider,
    ProviderResult,
)

# Note: base.py will be created in Task 1.2
# For now, these imports will fail, so we handle them gracefully
try:
    from .base import ExecutionProvider, ExecutionService
except ImportError:
    ExecutionService = None  # type: ignore
    ExecutionProvider = None  # type: ignore

__all__ = [
    "ExecutionType",
    "ExecutionStatus",
    "ExecutionRequest",
    "ExecutionResult",
    "ProviderResult",
    "CompilerType",
    "ImageProvider",
    "ExecutionService",
    "ExecutionProvider",
]
