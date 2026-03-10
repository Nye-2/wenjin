"""Sandbox module for isolated code and command execution.

This module provides:
- Sandbox ABC and data classes (base.py)
- Local and Docker sandbox providers (providers/)
- Virtual path mapping (paths.py)
- LangChain tool wrappers (tools.py)
- Configuration (config.py)

Legacy:
- SandboxExecutor (executor.py) - Use LocalSandbox instead
"""

from .base import CommandResult, FileInfo, Sandbox
from .config import SandboxSettings, get_sandbox_settings
from .exceptions import (
    SandboxError,
    SandboxNotFoundError,
    SandboxRuntimeError,
    SandboxTimeoutError,
)
from .paths import VirtualPathMapper
from .providers import LocalSandbox, LocalSandboxProvider, SandboxProvider
from .tools import (
    bash_tool,
    create_sandbox_tools,
    list_dir_tool,
    read_file_tool,
    str_replace_tool,
    write_file_tool,
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
    # Paths
    "VirtualPathMapper",
    # Providers
    "SandboxProvider",
    "LocalSandbox",
    "LocalSandboxProvider",
    # Configuration
    "SandboxSettings",
    "get_sandbox_settings",
    # Tools
    "bash_tool",
    "read_file_tool",
    "write_file_tool",
    "str_replace_tool",
    "list_dir_tool",
    "create_sandbox_tools",
    # Legacy
    "SandboxExecutor",
    "SandboxConfig",
    "ExecutionResult",
]
