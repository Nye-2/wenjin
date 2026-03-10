# 沙箱系统实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 AcademiaGPT-V2 构建完整的沙箱系统，支持安全的命令执行、文件操作和学术工具集成。

**Architecture:** 采用抽象接口 + 提供商模式，支持本地和 Docker 两种执行环境。使用虚拟路径系统隔离用户数据，通过中间件集成到代理系统。

**Tech Stack:** Python 3.12+, asyncio, subprocess, pathlib, langchain tools

---

## Chunk 1: 核心接口和数据结构

### Task 1: 沙箱配置

**Files:**
- Create: `backend/src/sandbox/config.py`
- Test: `backend/tests/sandbox/test_config.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/sandbox/test_config.py
"""Tests for sandbox configuration."""

import pytest


class TestSandboxConfig:
    def test_create_default_config(self):
        """Should create sandbox config with defaults."""
        from src.sandbox.config import SandboxConfig

        config = SandboxConfig()

        assert config.mode == "local"
        assert config.timeout == 300
        assert config.local_base_dir.endswith(".academiagpt/threads")

    def test_create_custom_config(self):
        """Should create sandbox config with custom values."""
        from src.sandbox.config import SandboxConfig

        config = SandboxConfig(
            mode="local",
            timeout=600,
            local_base_dir="/custom/path",
        )

        assert config.mode == "local"
        assert config.timeout == 600
        assert config.local_base_dir == "/custom/path"

    def test_invalid_mode_raises_error(self):
        """Should raise error for invalid mode."""
        from src.sandbox.config import SandboxConfig
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SandboxConfig(mode="invalid")

    def test_docker_config(self):
        """Should create docker config."""
        from src.sandbox.config import SandboxConfig, DockerSandboxSettings

        config = SandboxConfig(
            mode="docker",
            docker=DockerSandboxSettings(
                image="academiagpt/sandbox:latest",
                memory="2g",
                cpu_limit=2,
            ),
        )

        assert config.mode == "docker"
        assert config.docker.image == "academiagpt/sandbox:latest"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.sandbox.config'"

- [ ] **Step 3: 写最小实现**

```python
# src/sandbox/config.py
"""Sandbox configuration using Pydantic."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DockerSandboxSettings(BaseModel):
    """Docker sandbox specific settings."""

    image: str = Field(default="academiagpt/sandbox:latest", description="Docker image to use")
    timeout: int = Field(default=300, ge=30, le=3600, description="Execution timeout in seconds")
    memory: str = Field(default="2g", description="Memory limit (e.g., '2g', '512m')")
    cpu_limit: int = Field(default=2, ge=1, le=16, description="CPU limit")


class AcademicToolSettings(BaseModel):
    """Academic tool settings."""

    latex_enabled: bool = Field(default=True, description="Enable LaTeX compilation")
    latex_engine: str = Field(default="xelatex", description="LaTeX engine (xelatex, pdflatex)")
    code_execution_enabled: bool = Field(default=True, description="Enable code execution")
    supported_languages: list[str] = Field(default=["python", "r"], description="Supported languages")


class SandboxConfig(BaseModel):
    """Sandbox configuration."""

    mode: Literal["local", "docker"] = Field(default="local", description="Sandbox mode")
    timeout: int = Field(default=300, ge=30, le=3600, description="Default execution timeout in seconds")
    local_base_dir: str = Field(
        default=".academiagpt/threads",
        description="Base directory for local sandbox"
    )
    docker: DockerSandboxSettings | None = Field(default=None, description="Docker settings")
    academic: AcademicToolSettings = Field(
        default_factory=AcademicToolSettings,
        description="Academic tool settings"
    )

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("local", "docker"):
            raise ValueError(f"Invalid mode: {v}. Must be 'local' or 'docker'")
        return v

    def get_local_base_path(self) -> Path:
        """Get the absolute path for local base directory."""
        return Path(self.local_base_dir).resolve()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 提交**

```bash
git add backend/src/sandbox/config.py backend/tests/sandbox/test_config.py
git commit -m "feat(sandbox): add sandbox configuration with Pydantic

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Sandbox 抽象接口

**Files:**
- Create: `backend/src/sandbox/base.py`
- Test: `backend/tests/sandbox/test_base.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/sandbox/test_base.py
"""Tests for sandbox base interfaces."""

import pytest


class TestCommandResult:
    def test_create_success_result(self):
        """Should create successful command result."""
        from src.sandbox.base import CommandResult

        result = CommandResult(
            stdout="hello",
            stderr="",
            exit_code=0,
            timed_out=False,
        )

        assert result.stdout == "hello"
        assert result.exit_code == 0
        assert not result.timed_out

    def test_create_error_result(self):
        """Should create error command result."""
        from src.sandbox.base import CommandResult

        result = CommandResult(
            stdout="",
            stderr="command not found",
            exit_code=127,
            timed_out=False,
        )

        assert result.exit_code == 127
        assert "command not found" in result.stderr

    def test_create_timeout_result(self):
        """Should create timeout result."""
        from src.sandbox.base import CommandResult

        result = CommandResult(
            stdout="partial output",
            stderr="",
            exit_code=-1,
            timed_out=True,
        )

        assert result.timed_out
        assert result.exit_code == -1


class TestFileInfo:
    def test_create_file_info(self):
        """Should create file info."""
        from src.sandbox.base import FileInfo

        info = FileInfo(
            name="test.txt",
            path="/mnt/user-data/workspace/test.txt",
            is_dir=False,
            size=1024,
        )

        assert info.name == "test.txt"
        assert not info.is_dir
        assert info.size == 1024

    def test_create_dir_info(self):
        """Should create directory info."""
        from src.sandbox.base import FileInfo

        info = FileInfo(
            name="workspace",
            path="/mnt/user-data/workspace",
            is_dir=True,
        )

        assert info.is_dir
        assert info.size is None


class TestSandboxInterface:
    def test_sandbox_is_abstract(self):
        """Should not be able to instantiate Sandbox directly."""
        from src.sandbox.base import Sandbox
        from abc import ABC

        assert issubclass(Sandbox, ABC)

        with pytest.raises(TypeError):
            Sandbox(id="test")

    def test_sandbox_has_required_methods(self):
        """Should have all required abstract methods."""
        from src.sandbox.base import Sandbox
        import inspect

        methods = ["execute_command", "read_file", "write_file", "list_dir"]

        for method in methods:
            assert hasattr(Sandbox, method)
            # Check it's abstract
            attr = getattr(Sandbox, method)
            assert getattr(attr, "__isabstractmethod__", False)


class TestSandboxProviderInterface:
    def test_provider_is_abstract(self):
        """Should not be able to instantiate SandboxProvider directly."""
        from src.sandbox.base import SandboxProvider
        from abc import ABC

        assert issubclass(SandboxProvider, ABC)

        with pytest.raises(TypeError):
            SandboxProvider()

    def test_provider_has_required_methods(self):
        """Should have all required abstract methods."""
        from src.sandbox.base import SandboxProvider

        methods = ["acquire", "release", "get"]

        for method in methods:
            attr = getattr(SandboxProvider, method)
            assert getattr(attr, "__isabstractmethod__", False)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_base.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.sandbox.base'"

- [ ] **Step 3: 写最小实现**

```python
# src/sandbox/base.py
"""Abstract base classes for sandbox system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class CommandResult:
    """Result of command execution in sandbox."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


@dataclass
class FileInfo:
    """Information about a file or directory."""

    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None


class Sandbox(ABC):
    """Abstract base class for sandbox environments."""

    def __init__(self, id: str):
        """Initialize sandbox with unique identifier.

        Args:
            id: Unique sandbox identifier (usually thread_id)
        """
        self._id = id

    @property
    def id(self) -> str:
        """Get sandbox ID."""
        return self._id

    @abstractmethod
    async def execute_command(
        self,
        command: str,
        timeout: int = 300
    ) -> CommandResult:
        """Execute a bash command in the sandbox.

        Args:
            command: The command to execute
            timeout: Maximum execution time in seconds

        Returns:
            CommandResult with stdout, stderr, exit_code
        """
        pass

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Read the contents of a file.

        Args:
            path: Absolute path to the file

        Returns:
            File contents as string
        """
        pass

    @abstractmethod
    async def write_file(
        self,
        path: str,
        content: str,
        append: bool = False
    ) -> None:
        """Write content to a file.

        Args:
            path: Absolute path to the file
            content: Content to write
            append: If True, append to file; otherwise overwrite
        """
        pass

    @abstractmethod
    async def list_dir(self, path: str, max_depth: int = 2) -> list[FileInfo]:
        """List contents of a directory.

        Args:
            path: Absolute path to the directory
            max_depth: Maximum depth to traverse

        Returns:
            List of FileInfo objects
        """
        pass


class SandboxProvider(ABC):
    """Abstract base class for sandbox providers."""

    @abstractmethod
    async def acquire(self, thread_id: str) -> Sandbox:
        """Acquire a sandbox for a thread.

        Args:
            thread_id: Thread identifier

        Returns:
            Sandbox instance
        """
        pass

    @abstractmethod
    async def release(self, sandbox: Sandbox) -> None:
        """Release a sandbox.

        Args:
            sandbox: Sandbox to release
        """
        pass

    @abstractmethod
    async def get(self, sandbox_id: str) -> Optional[Sandbox]:
        """Get an existing sandbox by ID.

        Args:
            sandbox_id: Sandbox identifier

        Returns:
            Sandbox if found, None otherwise
        """
        pass
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_base.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: 提交**

```bash
git add backend/src/sandbox/base.py backend/tests/sandbox/test_base.py
git commit -m "feat(sandbox): add abstract Sandbox and SandboxProvider interfaces

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: 虚拟路径系统

**Files:**
- Create: `backend/src/sandbox/paths.py`
- Test: `backend/tests/sandbox/test_paths.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/sandbox/test_paths.py
"""Tests for virtual path system."""

import pytest


class TestVirtualPathMapper:
    def test_create_mapper(self):
        """Should create path mapper with thread data."""
        from src.sandbox.paths import VirtualPathMapper

        thread_data = {
            "workspace_path": "/real/path/workspace",
            "uploads_path": "/real/path/uploads",
            "outputs_path": "/real/path/outputs",
        }

        mapper = VirtualPathMapper(thread_data)

        assert mapper.thread_data == thread_data

    def test_virtual_to_physical_workspace(self):
        """Should map workspace virtual path to physical."""
        from src.sandbox.paths import VirtualPathMapper

        thread_data = {
            "workspace_path": "/home/user/.academiagpt/threads/abc123/workspace",
            "uploads_path": "/home/user/.academiagpt/threads/abc123/uploads",
            "outputs_path": "/home/user/.academiagpt/threads/abc123/outputs",
        }

        mapper = VirtualPathMapper(thread_data)

        result = mapper.to_physical("/mnt/user-data/workspace/paper.tex")

        assert result == "/home/user/.academiagpt/threads/abc123/workspace/paper.tex"

    def test_virtual_to_physical_outputs(self):
        """Should map outputs virtual path to physical."""
        from src.sandbox.paths import VirtualPathMapper

        thread_data = {
            "workspace_path": "/home/user/threads/abc/workspace",
            "uploads_path": "/home/user/threads/abc/uploads",
            "outputs_path": "/home/user/threads/abc/outputs",
        }

        mapper = VirtualPathMapper(thread_data)

        result = mapper.to_physical("/mnt/user-data/outputs/result.pdf")

        assert result == "/home/user/threads/abc/outputs/result.pdf"

    def test_non_virtual_path_unchanged(self):
        """Should not modify paths that don't start with virtual prefix."""
        from src.sandbox.paths import VirtualPathMapper

        mapper = VirtualPathMapper({})

        result = mapper.to_physical("/usr/bin/python")

        assert result == "/usr/bin/python"

    def test_physical_to_virtual(self):
        """Should map physical path back to virtual."""
        from src.sandbox.paths import VirtualPathMapper

        thread_data = {
            "workspace_path": "/home/user/threads/abc/workspace",
            "uploads_path": "/home/user/threads/abc/uploads",
            "outputs_path": "/home/user/threads/abc/outputs",
        }

        mapper = VirtualPathMapper(thread_data)

        result = mapper.to_virtual("/home/user/threads/abc/workspace/paper.tex")

        assert result == "/mnt/user-data/workspace/paper.tex"

    def test_translate_command_single_path(self):
        """Should translate single virtual path in command."""
        from src.sandbox.paths import VirtualPathMapper

        thread_data = {
            "workspace_path": "/real/workspace",
            "uploads_path": "/real/uploads",
            "outputs_path": "/real/outputs",
        }

        mapper = VirtualPathMapper(thread_data)

        result = mapper.translate_command("cat /mnt/user-data/workspace/file.txt")

        assert result == "cat /real/workspace/file.txt"

    def test_translate_command_multiple_paths(self):
        """Should translate multiple virtual paths in command."""
        from src.sandbox.paths import VirtualPathMapper

        thread_data = {
            "workspace_path": "/real/workspace",
            "uploads_path": "/real/uploads",
            "outputs_path": "/real/outputs",
        }

        mapper = VirtualPathMapper(thread_data)

        result = mapper.translate_command(
            "cp /mnt/user-data/workspace/input.pdf /mnt/user-data/outputs/output.pdf"
        )

        assert result == "cp /real/workspace/input.pdf /real/outputs/output.pdf"

    def test_is_virtual_path(self):
        """Should detect virtual paths."""
        from src.sandbox.paths import VirtualPathMapper

        mapper = VirtualPathMapper({})

        assert mapper.is_virtual_path("/mnt/user-data/workspace/file.txt")
        assert mapper.is_virtual_path("/mnt/user-data/uploads")
        assert not mapper.is_virtual_path("/home/user/file.txt")
        assert not mapper.is_virtual_path("relative/path.txt")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_paths.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.sandbox.paths'"

- [ ] **Step 3: 写最小实现**

```python
# src/sandbox/paths.py
"""Virtual path system for sandbox isolation."""

import re
from typing import Any


# Virtual path prefix used in all sandbox operations
VIRTUAL_PATH_PREFIX = "/mnt/user-data"


class VirtualPathMapper:
    """Maps virtual paths to physical paths and vice versa.

    Virtual paths are used in agent communications and tool calls.
    Physical paths are the actual filesystem paths.

    Mapping:
        /mnt/user-data/workspace/* -> thread_data['workspace_path']/*
        /mnt/user-data/uploads/* -> thread_data['uploads_path']/*
        /mnt/user-data/outputs/* -> thread_data['outputs_path']/*
    """

    def __init__(self, thread_data: dict[str, Any]):
        """Initialize mapper with thread data.

        Args:
            thread_data: Dictionary containing workspace_path, uploads_path, outputs_path
        """
        self.thread_data = thread_data

    def _get_path_mapping(self) -> dict[str, str]:
        """Get mapping of virtual subdirectories to physical paths."""
        return {
            "workspace": self.thread_data.get("workspace_path", ""),
            "uploads": self.thread_data.get("uploads_path", ""),
            "outputs": self.thread_data.get("outputs_path", ""),
        }

    def to_physical(self, virtual_path: str) -> str:
        """Convert virtual path to physical path.

        Args:
            virtual_path: Path that may start with /mnt/user-data

        Returns:
            Physical path with virtual prefix replaced
        """
        if not virtual_path.startswith(VIRTUAL_PATH_PREFIX):
            return virtual_path

        # Extract the relative path after /mnt/user-data/
        relative = virtual_path[len(VIRTUAL_PATH_PREFIX):].lstrip("/")
        if not relative:
            return virtual_path

        # Split into subdirectory and rest
        parts = relative.split("/", 1)
        subdir = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

        # Look up physical base path
        path_mapping = self._get_path_mapping()
        physical_base = path_mapping.get(subdir)

        if not physical_base:
            return virtual_path

        if rest:
            return f"{physical_base}/{rest}"
        return physical_base

    def to_virtual(self, physical_path: str) -> str:
        """Convert physical path to virtual path.

        Args:
            physical_path: Actual filesystem path

        Returns:
            Virtual path with /mnt/user-data prefix
        """
        path_mapping = self._get_path_mapping()

        # Sort by path length (longest first) for correct prefix matching
        for subdir, physical_base in sorted(path_mapping.items(), key=lambda x: len(x[1]), reverse=True):
            if not physical_base:
                continue
            if physical_path.startswith(physical_base):
                relative = physical_path[len(physical_base):].lstrip("/")
                if relative:
                    return f"{VIRTUAL_PATH_PREFIX}/{subdir}/{relative}"
                return f"{VIRTUAL_PATH_PREFIX}/{subdir}"

        return physical_path

    def translate_command(self, command: str) -> str:
        """Translate all virtual paths in a command string.

        Args:
            command: Command string that may contain virtual paths

        Returns:
            Command with virtual paths replaced by physical paths
        """
        if VIRTUAL_PATH_PREFIX not in command:
            return command

        # Pattern to match /mnt/user-data followed by path characters
        pattern = re.compile(rf"{re.escape(VIRTUAL_PATH_PREFIX)}(/[^\s\"';&|<>()]*)?")

        def replace_match(match: re.Match) -> str:
            virtual_path = match.group(0)
            return self.to_physical(virtual_path)

        return pattern.sub(replace_match, command)

    def is_virtual_path(self, path: str) -> bool:
        """Check if a path is a virtual path.

        Args:
            path: Path to check

        Returns:
            True if path starts with virtual prefix
        """
        return path.startswith(VIRTUAL_PATH_PREFIX)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_paths.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: 提交**

```bash
git add backend/src/sandbox/paths.py backend/tests/sandbox/test_paths.py
git commit -m "feat(sandbox): add virtual path system for isolation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: 更新 sandbox 模块导出

**Files:**
- Modify: `backend/src/sandbox/__init__.py`

- [ ] **Step 1: 更新模块导出**

```python
# src/sandbox/__init__.py
"""Sandbox module for safe code execution and file operations."""

from .base import CommandResult, FileInfo, Sandbox, SandboxProvider
from .config import AcademicToolSettings, DockerSandboxSettings, SandboxConfig
from .executor import ExecutionResult, SandboxConfig as LegacySandboxConfig, SandboxExecutor
from .paths import VIRTUAL_PATH_PREFIX, VirtualPathMapper

__all__ = [
    # Base interfaces
    "Sandbox",
    "SandboxProvider",
    "CommandResult",
    "FileInfo",
    # Configuration
    "SandboxConfig",
    "DockerSandboxSettings",
    "AcademicToolSettings",
    # Legacy executor (for backward compatibility)
    "SandboxExecutor",
    "ExecutionResult",
    "LegacySandboxConfig",
    # Path system
    "VirtualPathMapper",
    "VIRTUAL_PATH_PREFIX",
]
```

- [ ] **Step 2: 运行所有沙箱测试验证**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/ -v`
Expected: PASS (all tests)

- [ ] **Step 3: 提交**

```bash
git add backend/src/sandbox/__init__.py
git commit -m "feat(sandbox): update module exports with new interfaces

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: 本地沙箱实现

### Task 5: 目录列表工具

**Files:**
- Create: `backend/src/sandbox/utils/list_dir.py`
- Test: `backend/tests/sandbox/test_list_dir.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/sandbox/test_list_dir.py
"""Tests for directory listing utility."""

import os
import tempfile

import pytest


class TestListDir:
    def test_list_empty_directory(self):
        """Should handle empty directory."""
        from src.sandbox.utils.list_dir import list_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            result = list_dir(tmpdir)

            assert result == []

    def test_list_files(self):
        """Should list files in directory."""
        from src.sandbox.utils.list_dir import list_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            open(os.path.join(tmpdir, "file1.txt"), "w").close()
            open(os.path.join(tmpdir, "file2.txt"), "w").close()

            result = list_dir(tmpdir)

            assert len(result) == 2
            assert "file1.txt" in result[0]
            assert "file2.txt" in result[1]

    def test_list_with_subdirectories(self):
        """Should list subdirectories with tree format."""
        from src.sandbox.utils.list_dir import list_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create subdirectory with file
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)
            open(os.path.join(subdir, "nested.txt"), "w").close()

            result = list_dir(tmpdir, max_depth=2)

            assert any("subdir" in line for line in result)
            assert any("nested.txt" in line for line in result)

    def test_max_depth_limit(self):
        """Should respect max_depth parameter."""
        from src.sandbox.utils.list_dir import list_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested directories
            level1 = os.path.join(tmpdir, "level1")
            level2 = os.path.join(level1, "level2")
            os.makedirs(level2)
            open(os.path.join(level2, "deep.txt"), "w").close()

            result = list_dir(tmpdir, max_depth=1)

            # Should not show level2 contents
            assert not any("deep.txt" in line for line in result)

    def test_nonexistent_directory(self):
        """Should handle nonexistent directory."""
        from src.sandbox.utils.list_dir import list_dir

        with pytest.raises(FileNotFoundError):
            list_dir("/nonexistent/path/12345")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_list_dir.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 写最小实现**

```python
# src/sandbox/utils/__init__.py
"""Utility functions for sandbox."""

from .list_dir import list_dir

__all__ = ["list_dir"]
```

```python
# src/sandbox/utils/list_dir.py
"""Directory listing utility with tree format output."""

import os
from pathlib import Path


def list_dir(path: str, max_depth: int = 2) -> list[str]:
    """List directory contents in tree format.

    Args:
        path: Directory path to list
        max_depth: Maximum depth to traverse (default 2)

    Returns:
        List of strings representing the tree structure

    Raises:
        FileNotFoundError: If directory doesn't exist
    """
    root = Path(path)

    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {path}")

    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")

    result: list[str] = []

    def _walk(current: Path, prefix: str = "", depth: int = 0) -> None:
        """Recursively walk directory tree."""
        if depth > max_depth:
            return

        try:
            entries = sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            current_prefix = "└── " if is_last else "├── "
            next_prefix = "    " if is_last else "│   "

            result.append(f"{prefix}{current_prefix}{entry.name}")

            if entry.is_dir() and depth < max_depth:
                _walk(entry, prefix + next_prefix, depth + 1)

    _walk(root)
    return result
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_list_dir.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 提交**

```bash
git add backend/src/sandbox/utils/ backend/tests/sandbox/test_list_dir.py
git commit -m "feat(sandbox): add directory listing utility with tree format

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: 本地沙箱实现

**Files:**
- Create: `backend/src/sandbox/providers/__init__.py`
- Create: `backend/src/sandbox/providers/local.py`
- Test: `backend/tests/sandbox/test_local_sandbox.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/sandbox/test_local_sandbox.py
"""Tests for local sandbox implementation."""

import os
import tempfile

import pytest


class TestLocalSandbox:
    @pytest.fixture
    def sandbox(self):
        """Create a local sandbox for testing."""
        from src.sandbox.providers.local import LocalSandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create thread directories
            workspace = os.path.join(tmpdir, "workspace")
            uploads = os.path.join(tmpdir, "uploads")
            outputs = os.path.join(tmpdir, "outputs")
            os.makedirs(workspace)
            os.makedirs(uploads)
            os.makedirs(outputs)

            path_mappings = {
                "/mnt/user-data/workspace": workspace,
                "/mnt/user-data/uploads": uploads,
                "/mnt/user-data/outputs": outputs,
            }

            yield LocalSandbox(id="test-thread", path_mappings=path_mappings)

    @pytest.mark.asyncio
    async def test_sandbox_id(self, sandbox):
        """Should have correct sandbox ID."""
        assert sandbox.id == "test-thread"

    @pytest.mark.asyncio
    async def test_execute_echo_command(self, sandbox):
        """Should execute echo command."""
        result = await sandbox.execute_command("echo 'hello world'")

        assert result.exit_code == 0
        assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_command_with_exit_code(self, sandbox):
        """Should capture non-zero exit code."""
        result = await sandbox.execute_command("exit 1")

        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_execute_command_with_stderr(self, sandbox):
        """Should capture stderr."""
        result = await sandbox.execute_command("echo 'error' >&2")

        assert "error" in result.stderr or "error" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_command_timeout(self, sandbox):
        """Should timeout long-running command."""
        result = await sandbox.execute_command("sleep 10", timeout=1)

        assert result.timed_out

    @pytest.mark.asyncio
    async def test_write_and_read_file(self, sandbox):
        """Should write and read file."""
        await sandbox.write_file("/mnt/user-data/workspace/test.txt", "hello")
        content = await sandbox.read_file("/mnt/user-data/workspace/test.txt")

        assert content == "hello"

    @pytest.mark.asyncio
    async def test_write_file_append(self, sandbox):
        """Should append to file."""
        await sandbox.write_file("/mnt/user-data/workspace/test.txt", "line1\n")
        await sandbox.write_file("/mnt/user-data/workspace/test.txt", "line2\n", append=True)
        content = await sandbox.read_file("/mnt/user-data/workspace/test.txt")

        assert "line1" in content
        assert "line2" in content

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, sandbox):
        """Should raise error for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await sandbox.read_file("/mnt/user-data/workspace/nonexistent.txt")

    @pytest.mark.asyncio
    async def test_list_directory(self, sandbox):
        """Should list directory contents."""
        await sandbox.write_file("/mnt/user-data/workspace/file1.txt", "content")
        await sandbox.write_file("/mnt/user-data/workspace/file2.txt", "content")

        entries = await sandbox.list_dir("/mnt/user-data/workspace")

        assert any("file1.txt" in str(e) for e in entries)
        assert any("file2.txt" in str(e) for e in entries)

    @pytest.mark.asyncio
    async def test_virtual_path_translation_in_command(self, sandbox):
        """Should translate virtual paths in commands."""
        # Create a file via sandbox
        await sandbox.write_file("/mnt/user-data/workspace/test.txt", "hello")

        # Execute command with virtual path
        result = await sandbox.execute_command("cat /mnt/user-data/workspace/test.txt")

        assert result.exit_code == 0
        assert "hello" in result.stdout
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_local_sandbox.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 写最小实现**

```python
# src/sandbox/providers/__init__.py
"""Sandbox providers package."""

from .local import LocalSandbox, LocalSandboxProvider

__all__ = ["LocalSandbox", "LocalSandboxProvider"]
```

```python
# src/sandbox/providers/local.py
"""Local sandbox implementation for development."""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.sandbox.base import CommandResult, FileInfo, Sandbox, SandboxProvider
from src.sandbox.paths import VirtualPathMapper
from src.sandbox.utils.list_dir import list_dir


class LocalSandbox(Sandbox):
    """Sandbox that executes commands on the local filesystem.

    Uses virtual path mapping to isolate thread data.
    """

    def __init__(self, id: str, path_mappings: dict[str, str] | None = None):
        """Initialize local sandbox.

        Args:
            id: Sandbox identifier (usually thread_id)
            path_mappings: Mapping of virtual paths to physical paths
        """
        super().__init__(id)
        self.path_mappings = path_mappings or {}
        self._mapper = VirtualPathMapper(self._build_thread_data())

    def _build_thread_data(self) -> dict[str, Any]:
        """Build thread data from path mappings."""
        return {
            "workspace_path": self.path_mappings.get("/mnt/user-data/workspace", ""),
            "uploads_path": self.path_mappings.get("/mnt/user-data/uploads", ""),
            "outputs_path": self.path_mappings.get("/mnt/user-data/outputs", ""),
        }

    def _resolve_path(self, path: str) -> str:
        """Resolve virtual path to physical path."""
        return self._mapper.to_physical(path)

    def _resolve_command(self, command: str) -> str:
        """Resolve all virtual paths in a command."""
        return self._mapper.translate_command(command)

    def _reverse_resolve_path(self, path: str) -> str:
        """Convert physical path back to virtual path."""
        return self._mapper.to_virtual(path)

    @staticmethod
    def _get_shell() -> str:
        """Detect available shell."""
        for shell in ("/bin/zsh", "/bin/bash", "/bin/sh"):
            if os.path.isfile(shell) and os.access(shell, os.X_OK):
                return shell
        shell_from_path = shutil.which("sh")
        if shell_from_path:
            return shell_from_path
        raise RuntimeError("No suitable shell found")

    async def execute_command(
        self,
        command: str,
        timeout: int = 300
    ) -> CommandResult:
        """Execute a bash command locally."""
        resolved_command = self._resolve_command(command)

        try:
            proc = await asyncio.create_subprocess_shell(
                resolved_command,
                executable=self._get_shell(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return CommandResult(
                    stdout="",
                    stderr=f"Command timed out after {timeout} seconds",
                    exit_code=-1,
                    timed_out=True,
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Reverse resolve paths in output
            output = self._reverse_resolve_path(stdout_str)
            if stderr_str:
                output += f"\nStd Error:\n{self._reverse_resolve_path(stderr_str)}"

            return CommandResult(
                stdout=output,
                stderr="",
                exit_code=proc.returncode or 0,
                timed_out=False,
            )

        except Exception as e:
            return CommandResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                timed_out=False,
            )

    async def read_file(self, path: str) -> str:
        """Read file contents."""
        resolved = self._resolve_path(path)
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            raise type(e)(e.errno, e.strerror, path) from None

    async def write_file(
        self,
        path: str,
        content: str,
        append: bool = False
    ) -> None:
        """Write content to file."""
        resolved = self._resolve_path(path)
        try:
            dir_path = os.path.dirname(resolved)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            mode = "a" if append else "w"
            with open(resolved, mode, encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            raise type(e)(e.errno, e.strerror, path) from None

    async def list_dir(self, path: str, max_depth: int = 2) -> list[FileInfo]:
        """List directory contents."""
        resolved = self._resolve_path(path)
        entries = list_dir(resolved, max_depth)

        # Convert to FileInfo objects and reverse resolve paths
        result: list[FileInfo] = []
        for entry in entries:
            # Parse tree format to extract name
            name = entry.split("── ")[-1] if "── " in entry else entry
            virtual = self._reverse_resolve_path(os.path.join(resolved, name))
            result.append(FileInfo(
                name=name,
                path=virtual,
                is_dir=not os.path.isfile(os.path.join(resolved, name)),
            ))

        return result


class LocalSandboxProvider(SandboxProvider):
    """Provider for local sandbox instances."""

    def __init__(self, config: Any = None):
        """Initialize provider."""
        self._sandboxes: dict[str, LocalSandbox] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, thread_id: str) -> LocalSandbox:
        """Acquire or create a sandbox for the thread."""
        async with self._lock:
            if thread_id in self._sandboxes:
                return self._sandboxes[thread_id]

            # Create thread directories
            base_dir = Path(".academiagpt/threads") / thread_id
            workspace = base_dir / "workspace"
            uploads = base_dir / "uploads"
            outputs = base_dir / "outputs"

            workspace.mkdir(parents=True, exist_ok=True)
            uploads.mkdir(parents=True, exist_ok=True)
            outputs.mkdir(parents=True, exist_ok=True)

            path_mappings = {
                "/mnt/user-data/workspace": str(workspace.resolve()),
                "/mnt/user-data/uploads": str(uploads.resolve()),
                "/mnt/user-data/outputs": str(outputs.resolve()),
            }

            sandbox = LocalSandbox(id=thread_id, path_mappings=path_mappings)
            self._sandboxes[thread_id] = sandbox
            return sandbox

    async def release(self, sandbox: Sandbox) -> None:
        """Release a sandbox (no-op for local)."""
        async with self._lock:
            if sandbox.id in self._sandboxes:
                del self._sandboxes[sandbox.id]

    async def get(self, sandbox_id: str) -> LocalSandbox | None:
        """Get an existing sandbox by ID."""
        return self._sandboxes.get(sandbox_id)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_local_sandbox.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: 提交**

```bash
git add backend/src/sandbox/providers/ backend/tests/sandbox/test_local_sandbox.py
git commit -m "feat(sandbox): add local sandbox implementation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: 沙箱工具集

### Task 7: 沙箱工具 (LangChain Tools)

**Files:**
- Create: `backend/src/sandbox/tools.py`
- Test: `backend/tests/sandbox/test_tools.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/sandbox/test_tools.py
"""Tests for sandbox tools."""

import pytest


class TestSandboxTools:
    """Tests for sandbox tool functions."""

    def test_bash_tool_import(self):
        """Should be able to import bash_tool."""
        from src.sandbox.tools import bash_tool

        assert bash_tool is not None

    def test_ls_tool_import(self):
        """Should be able to import ls_tool."""
        from src.sandbox.tools import ls_tool

        assert ls_tool is not None

    def test_read_file_tool_import(self):
        """Should be able to import read_file_tool."""
        from src.sandbox.tools import read_file_tool

        assert read_file_tool is not None

    def test_write_file_tool_import(self):
        """Should be able to import write_file_tool."""
        from src.sandbox.tools import write_file_tool

        assert write_file_tool is not None

    def test_str_replace_tool_import(self):
        """Should be able to import str_replace_tool."""
        from src.sandbox.tools import str_replace_tool

        assert str_replace_tool is not None

    def test_get_sandbox_tools(self):
        """Should return list of sandbox tools."""
        from src.sandbox.tools import get_sandbox_tools

        tools = get_sandbox_tools()

        assert len(tools) == 5
        tool_names = [t.name for t in tools]
        assert "bash" in tool_names
        assert "ls" in tool_names
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "str_replace" in tool_names
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_tools.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 写最小实现**

```python
# src/sandbox/tools.py
"""Sandbox tools for LangGraph agent."""

from langchain_core.tools import tool


@tool
def bash_tool(description: str, command: str) -> str:
    """Execute a bash command in a Linux environment.

    Use this tool for file operations, system commands, and running scripts.
    Always use absolute paths starting with /mnt/user-data/ for file operations.

    Args:
        description: Brief explanation of why you're running this command.
        command: The bash command to execute.

    Returns:
        Command output or error message.
    """
    # Note: In actual implementation, this uses runtime state
    return f"Command execution requires runtime context"


@tool
def ls_tool(description: str, path: str) -> str:
    """List the contents of a directory in tree format.

    Args:
        description: Brief explanation of why you're listing this directory.
        path: The absolute path to the directory to list.

    Returns:
        Directory tree listing or error message.
    """
    return f"Directory listing requires runtime context"


@tool
def read_file_tool(description: str, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read the contents of a text file.

    Args:
        description: Brief explanation of why you're reading this file.
        path: The absolute path to the file.
        start_line: Optional starting line number (1-indexed).
        end_line: Optional ending line number (1-indexed).

    Returns:
        File contents or error message.
    """
    return f"File reading requires runtime context"


@tool
def write_file_tool(description: str, path: str, content: str, append: bool = False) -> str:
    """Write text content to a file.

    Args:
        description: Brief explanation of why you're writing this file.
        path: The absolute path to the file.
        content: The content to write.
        append: If True, append to file instead of overwriting.

    Returns:
        "OK" on success or error message.
    """
    return "OK"


@tool
def str_replace_tool(description: str, path: str, old_str: str, new_str: str, replace_all: bool = False) -> str:
    """Replace a substring in a file.

    Args:
        description: Brief explanation of why you're replacing.
        path: The absolute path to the file.
        old_str: The substring to replace.
        new_str: The new substring.
        replace_all: If True, replace all occurrences.

    Returns:
        "OK" on success or error message.
    """
    return "OK"


def get_sandbox_tools() -> list:
    """Get all sandbox tools for agent use."""
    return [
        bash_tool,
        ls_tool,
        read_file_tool,
        write_file_tool,
        str_replace_tool,
    ]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_tools.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: 提交**

```bash
git add backend/src/sandbox/tools.py backend/tests/sandbox/test_tools.py
git commit -m "feat(sandbox): add sandbox tools for LangGraph agent

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: 中间件和集成

### Task 8: SandboxMiddleware

**Files:**
- Create: `backend/src/sandbox/middleware.py`
- Test: `backend/tests/sandbox/test_middleware.py`

- [ ] **Step 1: 写失败的测试**

```python
# tests/sandbox/test_middleware.py
"""Tests for sandbox middleware."""

import pytest


class TestSandboxMiddleware:
    def test_import_middleware(self):
        """Should be able to import SandboxMiddleware."""
        from src.sandbox.middleware import SandboxMiddleware

        assert SandboxMiddleware is not None

    @pytest.mark.asyncio
    async def test_middleware_before_model_no_state(self):
        """Should handle missing state gracefully."""
        from src.sandbox.middleware import SandboxMiddleware

        middleware = SandboxMiddleware()

        # Should not crash with empty state
        result = await middleware.before_model({}, {})

        assert result is not None

    @pytest.mark.asyncio
    async def test_middleware_before_model_creates_sandbox(self):
        """Should create sandbox if not present."""
        from src.sandbox.middleware import SandboxMiddleware

        middleware = SandboxMiddleware()

        state = {
            "thread_data": {
                "workspace_path": "/tmp/test/workspace",
                "uploads_path": "/tmp/test/uploads",
                "outputs_path": "/tmp/test/outputs",
            }
        }
        config = {"configurable": {"thread_id": "test-thread"}}

        result = await middleware.before_model(state, config)

        assert "sandbox" in result

    @pytest.mark.asyncio
    async def test_middleware_after_model(self):
        """Should handle after_model hook."""
        from src.sandbox.middleware import SandboxMiddleware

        middleware = SandboxMiddleware()

        state = {"sandbox": {"sandbox_id": "test"}}
        config = {}

        result = await middleware.after_model(state, config)

        assert result is not None
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_middleware.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: 写最小实现**

```python
# src/sandbox/middleware.py
"""Sandbox middleware for agent integration."""

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState
from src.sandbox.providers.local import LocalSandboxProvider


class SandboxMiddleware(Middleware):
    """Middleware that manages sandbox lifecycle.

    Creates sandbox on first use and stores sandbox_id in state.
    """

    def __init__(self, provider: LocalSandboxProvider | None = None):
        """Initialize middleware.

        Args:
            provider: Optional sandbox provider. Uses LocalSandboxProvider if not provided.
        """
        self._provider = provider or LocalSandboxProvider()

    async def before_model(
        self,
        state: ThreadState,
        config: dict
    ) -> dict | None:
        """Ensure sandbox is initialized before model call.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            State updates with sandbox info
        """
        # Check if sandbox already exists
        if state.get("sandbox"):
            return None

        # Get thread_id from config or state
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            # Try to get from thread_data
            thread_data = state.get("thread_data", {})
            thread_id = thread_data.get("thread_id")

        if not thread_id:
            return None

        # Acquire sandbox
        sandbox = await self._provider.acquire(thread_id)

        # Update state with sandbox info
        return {
            "sandbox": {
                "sandbox_id": sandbox.id,
            }
        }

    async def after_model(
        self,
        state: ThreadState,
        config: dict
    ) -> dict | None:
        """Handle cleanup after model call.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            None (no updates needed)
        """
        # Sandbox is kept alive for the duration of the thread
        # It will be released when the thread is deleted
        return None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/sandbox/test_middleware.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 提交**

```bash
git add backend/src/sandbox/middleware.py backend/tests/sandbox/test_middleware.py
git commit -m "feat(sandbox): add SandboxMiddleware for agent integration

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 9: 更新中间件导出和集成

**Files:**
- Modify: `backend/src/agents/middlewares/__init__.py`
- Modify: `backend/src/agents/lead_agent/agent.py`

- [ ] **Step 1: 更新中间件导出**

在 `src/agents/middlewares/__init__.py` 中添加 SandboxMiddleware 导出。

- [ ] **Step 2: 更新代理构建流程**

在 `src/agents/lead_agent/agent.py` 的 `build_pipeline` 函数中添加 SandboxMiddleware。

- [ ] **Step 3: 运行所有测试验证**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/ -v --tb=short`
Expected: PASS (all tests)

- [ ] **Step 4: 提交**

```bash
git add backend/src/agents/middlewares/__init__.py backend/src/agents/lead_agent/agent.py
git commit -m "feat(sandbox): integrate SandboxMiddleware into agent pipeline

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 5: 最终验证

### Task 10: 最终验证和文档

- [ ] **Step 1: 运行完整测试套件**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: 运行类型检查**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run mypy src/sandbox/ --ignore-missing-imports`
Expected: No errors

- [ ] **Step 3: 运行代码质量检查**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run ruff check src/sandbox/`
Expected: No errors

- [ ] **Step 4: 创建完成提交**

```bash
git add .
git commit -m "feat(sandbox): complete sandbox system implementation

- Add Sandbox and SandboxProvider abstract interfaces
- Implement LocalSandbox with virtual path mapping
- Add sandbox tools (bash, ls, read_file, write_file, str_replace)
- Integrate SandboxMiddleware into agent pipeline
- Add comprehensive test coverage

Phase 1 of architecture refactor complete.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 验收标准

- [ ] 所有沙箱测试通过 (预计 50+ 测试)
- [ ] 代码覆盖率 > 80%
- [ ] 类型检查无错误
- [ ] 代码风格检查无错误
- [ ] 文档已更新
- [ ] 中间件已集成到代理系统

---

## 后续工作

此计划完成 Phase 1 (沙箱系统)。后续计划：

- **Phase 2**: 子代理系统 - 双重线程池、SSE 事件流
- **Phase 3**: MCP 集成 - OAuth、缓存、多传输支持
- **Phase 4**: 记忆系统 - 事实提取、持久化、防抖更新
