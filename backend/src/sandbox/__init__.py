"""Sandbox module for safe code execution and file operations."""

# Core
from .base import CommandResult, FileInfo, Sandbox

# Configuration
from .config import (
    AcademicToolsConfig,
    CodeExecutionConfig,
    DockerSandboxConfig,
    LaTeXConfig,
    LocalSandboxConfig,
    SandboxSettings,
    get_sandbox_settings,
)

# Exceptions
from .exceptions import (
    SandboxError,
    SandboxNotFoundError,
    SandboxRuntimeError,
    SandboxTimeoutError,
)

# Path management
from .paths import VirtualPathMapper
from .providers.base import SandboxProvider

# Providers
from .providers.local import LocalSandbox, LocalSandboxProvider

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
    "LocalSandboxConfig",
    "DockerSandboxConfig",
    "LaTeXConfig",
    "CodeExecutionConfig",
    "AcademicToolsConfig",
    # Providers
    "SandboxProvider",
    "LocalSandbox",
    "LocalSandboxProvider",
    # Legacy
    "SandboxExecutor",
    "SandboxConfig",
    "ExecutionResult",
]
