"""Sandbox module for safe code execution and file operations."""

# Core
from .base import CommandResult, FileInfo, Sandbox

# Exceptions
from .exceptions import (
    SandboxError,
    SandboxNotFoundError,
    SandboxRuntimeError,
    SandboxTimeoutError,
)

# Path management
from .paths import VirtualPathMapper

# Configuration
from .config import SandboxSettings, get_sandbox_settings

# Providers
from .providers.local import LocalSandbox, LocalSandboxProvider
from .providers.base import SandboxProvider

# Tools
from .tools import (
    bash,
    ls,
    read_file,
    write_file,
    str_replace,
    create_sandbox_tools,
)

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
    # Configuration
    "SandboxSettings",
    "get_sandbox_settings",
    # Providers
    "SandboxProvider",
    "LocalSandbox",
    "LocalSandboxProvider",
    # Tools
    "bash",
    "ls",
    "read_file",
    "write_file",
    "str_replace",
    "create_sandbox_tools",
    # Legacy
    "SandboxExecutor",
    "SandboxConfig",
    "ExecutionResult",
]
