"""Sandbox module for safe code execution and file operations."""

from .base import CommandResult, FileInfo, Sandbox
from .exceptions import (
    SandboxError,
    SandboxNotFoundError,
    SandboxRuntimeError,
    SandboxTimeoutError,
)
from .paths import VirtualPathMapper
from .providers.local import LocalSandbox, LocalSandboxProvider
from .tools import create_sandbox_tools

# Legacy imports (backward compatibility)
try:
    from .executor import ExecutionResult, SandboxConfig, SandboxExecutor
except ImportError:
    pass

__all__ = [
    # Core
    "Sandbox",
    "CommandResult",
    "FileInfo",
    # Exceptions
    "SandboxError",
    "SandboxNotFoundError",
    "SandboxRuntimeError",
    "SandboxTimeoutError",
    # Path management
    "VirtualPathMapper",
    # Sandbox providers
    "LocalSandbox",
    "LocalSandboxProvider",
    # Tools
    "create_sandbox_tools",
    # Legacy
    "SandboxExecutor",
    "SandboxConfig",
    "ExecutionResult",
]
