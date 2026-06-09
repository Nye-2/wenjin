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
from .providers.docker import DockerSandbox, DockerSandboxProvider
from .providers.local import LocalSandbox, LocalSandboxProvider
from .workspace_layout import (
    WORKSPACE_MANIFEST_RELATIVE_PATH,
    WORKSPACE_PATH_CLASSES,
    WORKSPACE_PROTECTED_PATHS,
    WORKSPACE_ROOT,
    WORKSPACE_STANDARD_DIRS,
    WORKSPACE_SUPPORTED_TYPES,
    WORKSPACE_TYPE_PROFILE_SCHEMA,
    ensure_workspace_sandbox_layout,
    is_workspace_guidance_path,
    validate_workspace_type_profile,
    workspace_type_profile,
    workspace_virtual_path,
)

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
    "WORKSPACE_ROOT",
    "WORKSPACE_STANDARD_DIRS",
    "WORKSPACE_SUPPORTED_TYPES",
    "WORKSPACE_PATH_CLASSES",
    "WORKSPACE_PROTECTED_PATHS",
    "WORKSPACE_TYPE_PROFILE_SCHEMA",
    "WORKSPACE_MANIFEST_RELATIVE_PATH",
    "ensure_workspace_sandbox_layout",
    "is_workspace_guidance_path",
    "validate_workspace_type_profile",
    "workspace_type_profile",
    "workspace_virtual_path",
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
    "DockerSandbox",
    "DockerSandboxProvider",
    "LocalSandbox",
    "LocalSandboxProvider",
]
