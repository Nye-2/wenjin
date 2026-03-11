# Execution Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add LaTeX compilation, Python plotting, diagram generation, and AI image generation capabilities to the sandbox using Docker container isolation.

**Architecture:** Two-layer design with semantic Tools for direct LLM use, DockerExecutionService for container orchestration, and specialized Providers for each execution type. Abstract interfaces allow future migration to microservices.

**Tech Stack:** Docker SDK for Python, LangChain Tools, Pydantic models, async/await patterns

---

## Phase 1: Core Types and Interfaces

### Task 1.1: Create Execution Types

**Files:**
- Create: `src/execution/__init__.py`
- Create: `src/execution/types.py`

**Step 1: Create the execution package directory**

```bash
mkdir -p backend/src/execution
mkdir -p backend/src/execution/providers
mkdir -p backend/src/execution/docker
mkdir -p backend/src/execution/security
mkdir -p backend/tests/execution
```

**Step 2: Create `src/execution/__init__.py`**

```python
"""Execution service for LaTeX, Python, diagram, and AI image generation."""

from .types import (
    ExecutionType,
    ExecutionStatus,
    ExecutionRequest,
    ExecutionResult,
    ProviderResult,
    CompilerType,
    ImageProvider,
)
from .base import ExecutionService, ExecutionProvider

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
```

**Step 3: Create `src/execution/types.py`**

```python
"""Data types for execution service."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ExecutionType(Enum):
    """Execution type."""
    LATEX_COMPILE = "latex_compile"
    PYTHON_PLOT = "python_plot"
    MERMAID_DIAGRAM = "mermaid_diagram"
    AI_IMAGE = "ai_image"


class ExecutionStatus(Enum):
    """Execution status."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SECURITY_VIOLATION = "security_violation"


class CompilerType(Enum):
    """LaTeX compiler type."""
    PDFLATEX = "pdflatex"
    XELATEX = "xelatex"


class ImageProvider(Enum):
    """AI image generation provider."""
    KLING = "kling"
    DALLE = "dalle"


@dataclass
class ExecutionRequest:
    """Execution request."""
    execution_type: ExecutionType
    content: str  # Source code or prompt
    options: dict[str, Any] = field(default_factory=dict)
    timeout: int = 120
    workspace_id: Optional[str] = None
    thread_id: Optional[str] = None
    output_filename: Optional[str] = None


@dataclass
class ProviderResult:
    """Provider execution result (internal)."""
    success: bool
    output_files: list[str] = field(default_factory=list)  # Relative to work_dir
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    logs: Optional[str] = None


@dataclass
class ExecutionResult:
    """Execution result (returned to Tool)."""
    status: ExecutionStatus
    sandbox_path: Optional[str] = None  # Virtual path like /mnt/user-data/...
    artifact_id: Optional[str] = None
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    logs: Optional[str] = None
    source_code: Optional[str] = None

    def to_tool_output(self) -> str:
        """Convert to tool return string."""
        if self.status == ExecutionStatus.SUCCESS:
            msg = f"Success. Output saved to: {self.sandbox_path}"
            if self.metadata.get("page_count"):
                msg += f" ({self.metadata['page_count']} pages)"
            return msg
        return f"Failed: {self.error_message}"
```

**Step 4: Run tests to verify module imports**

Run: `cd backend && python -c "from src.execution import ExecutionType, ExecutionStatus; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add src/execution/__init__.py src/execution/types.py
git commit -m "feat(execution): add core types for execution service"
```

---

### Task 1.2: Create Base Interfaces

**Files:**
- Create: `src/execution/base.py`
- Create: `src/execution/providers/__init__.py`
- Create: `tests/execution/__init__.py`
- Create: `tests/execution/test_base.py`

**Step 1: Write the failing test**

Create `tests/execution/test_base.py`:

```python
"""Tests for execution base interfaces."""

import pytest
from src.execution.base import ExecutionService, ExecutionProvider
from src.execution.types import ExecutionRequest, ExecutionResult, ExecutionType, ExecutionStatus


class TestExecutionServiceInterface:
    """Tests for ExecutionService abstract interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Should not be able to instantiate abstract class."""
        with pytest.raises(TypeError):
            ExecutionService()

    def test_subclass_must_implement_execute(self):
        """Subclass must implement execute method."""
        class IncompleteService(ExecutionService):
            pass

        with pytest.raises(TypeError):
            IncompleteService()


class TestExecutionProviderInterface:
    """Tests for ExecutionProvider abstract interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Should not be able to instantiate abstract class."""
        with pytest.raises(TypeError):
            ExecutionProvider()

    def test_subclass_must_implement_required_methods(self):
        """Subclass must implement all required methods."""
        class IncompleteProvider(ExecutionProvider):
            @property
            def execution_type(self) -> str:
                return "test"

        with pytest.raises(TypeError):
            IncompleteProvider()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/execution/test_base.py -v`
Expected: FAIL with "TypeError" or "Can't instantiate abstract class"

**Step 3: Create `src/execution/base.py`**

```python
"""Abstract base classes for execution service."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .types import ExecutionRequest, ExecutionResult, ProviderResult


class ExecutionService(ABC):
    """Abstract execution service interface.

    Allows future migration to microservices architecture.
    """

    @abstractmethod
    async def execute(self, request: "ExecutionRequest") -> "ExecutionResult":
        """Execute a task.

        Args:
            request: Execution request with type, content, and options.

        Returns:
            ExecutionResult with status and output path.
        """
        pass

    @abstractmethod
    async def health_check(self) -> dict:
        """Check service health.

        Returns:
            Health status dictionary.
        """
        pass


class ExecutionProvider(ABC):
    """Abstract execution provider.

    Each provider handles a specific execution type.
    """

    @property
    @abstractmethod
    def execution_type(self) -> str:
        """Execution type this provider handles."""
        pass

    @property
    @abstractmethod
    def docker_image(self) -> Optional[str]:
        """Docker image name, or None if no Docker needed."""
        pass

    def build_command(self, content: str, options: dict) -> list[str]:
        """Build Docker command for execution.

        Args:
            content: Source code or prompt.
            options: Execution options.

        Returns:
            Command list for Docker execution.
        """
        return []

    @abstractmethod
    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict,
        docker_client: Optional[object] = None,
    ) -> "ProviderResult":
        """Execute the task.

        Args:
            content: Source code or prompt.
            work_dir: Working directory path.
            options: Execution options.
            docker_client: Optional Docker client.

        Returns:
            ProviderResult with output files and metadata.
        """
        pass

    async def process_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        work_dir: str,
        options: dict,
    ) -> "ProviderResult":
        """Process Docker execution result.

        Override this if using Docker execution.

        Args:
            exit_code: Container exit code.
            stdout: Container stdout.
            stderr: Container stderr.
            work_dir: Working directory path.
            options: Execution options.

        Returns:
            ProviderResult with output files.
        """
        raise NotImplementedError("Override for Docker-based providers")
```

**Step 4: Create `src/execution/providers/__init__.py`**

```python
"""Execution providers package."""

from ..base import ExecutionProvider

__all__ = ["ExecutionProvider"]
```

**Step 5: Create `tests/execution/__init__.py`**

```python
"""Tests for execution service."""
```

**Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/execution/test_base.py -v`
Expected: PASS (3 tests)

**Step 7: Commit**

```bash
git add src/execution/base.py src/execution/providers/__init__.py tests/execution/__init__.py tests/execution/test_base.py
git commit -m "feat(execution): add abstract base interfaces"
```

---

### Task 1.3: Create Security Sanitizers

**Files:**
- Create: `src/execution/security/__init__.py`
- Create: `src/execution/security/latex_sanitizer.py`
- Create: `src/execution/security/python_sanitizer.py`
- Create: `tests/execution/test_sanitizers.py`

**Step 1: Write the failing test**

Create `tests/execution/test_sanitizers.py`:

```python
"""Tests for security sanitizers."""

import pytest
from src.execution.security.latex_sanitizer import sanitize_latex
from src.execution.security.python_sanitizer import sanitize_python


class TestLatexSanitizer:
    """Tests for LaTeX security sanitizer."""

    def test_allows_safe_latex(self):
        """Should allow safe LaTeX code."""
        safe_latex = r"""
        \documentclass{article}
        \begin{document}
        Hello World
        \end{document}
        """
        is_safe, error = sanitize_latex(safe_latex)
        assert is_safe is True
        assert error == ""

    def test_blocks_write18(self):
        """Should block \\write18 command."""
        malicious = r"\write18{rm -rf /}"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False
        assert "write18" in error.lower()

    def test_blocks_shell_escape(self):
        """Should block shell-escape."""
        malicious = r"\documentclass[shell-escape]{article}"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False

    def test_blocks_input_pipe(self):
        """Should block \\input{|...} pattern."""
        malicious = r"\input{|cat /etc/passwd}"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False

    def test_blocks_catcode_manipulation(self):
        """Should block catcode manipulation."""
        malicious = r"\catcode`|=0"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False


class TestPythonSanitizer:
    """Tests for Python AST sanitizer."""

    def test_allows_safe_imports(self):
        """Should allow safe imports."""
        safe_code = "import numpy as np\nimport matplotlib.pyplot as plt"
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True

    def test_blocks_os_import(self):
        """Should block os module import."""
        malicious = "import os\nos.system('rm -rf /')"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False
        assert "os" in error

    def test_blocks_subprocess_import(self):
        """Should block subprocess module."""
        malicious = "import subprocess"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_blocks_eval(self):
        """Should block eval function."""
        malicious = "eval('__import__(\"os\").system(\"id\")')"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_blocks_exec(self):
        """Should block exec function."""
        malicious = "exec('print(1)')"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_allows_matplotlib_savefig(self):
        """Should allow matplotlib savefig."""
        safe_code = """
import matplotlib.pyplot as plt
plt.plot([1,2,3])
plt.savefig('output.png')
"""
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True

    def test_handles_syntax_error(self):
        """Should handle syntax errors gracefully."""
        invalid_code = "def broken("
        is_safe, error = sanitize_python(invalid_code)
        assert is_safe is False
        assert "syntax" in error.lower()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/execution/test_sanitizers.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create `src/execution/security/__init__.py`**

```python
"""Security sanitizers for execution service."""

from .latex_sanitizer import sanitize_latex
from .python_sanitizer import sanitize_python

__all__ = ["sanitize_latex", "sanitize_python"]
```

**Step 4: Create `src/execution/security/latex_sanitizer.py`**

```python
"""LaTeX source code security sanitizer."""

import re
from typing import Tuple


# Dangerous LaTeX commands/patterns
DANGEROUS_PATTERNS = [
    (r"\\write18", "write18 command is forbidden"),
    (r"\\immediate\s*\\write", "immediate write is forbidden"),
    (r"\\input\s*\{?\|", "input with pipe is forbidden"),
    (r"\\includegraphics.*\|", "includegraphics with pipe is forbidden"),
    (r"shell-escape", "shell-escape option is forbidden"),
    (r"\\catcode", "catcode manipulation is forbidden"),
    (r"\\endlinechar", "endlinechar manipulation is forbidden"),
    (r"\\everyfooter", "everyfooter is forbidden"),
    (r"\\everyheader", "everyheader is forbidden"),
    (r"\\special\s*\{", "special command is forbidden"),
    (r"\\pdffilespec", "pdffilespec is forbidden"),
    (r"\\pdfannot", "pdfannot is forbidden"),
    (r"\\pdflastlink", "pdflastlink is forbidden"),
    (r"\\pdfoutline", "pdfoutline is forbidden"),
    (r"\\ifnum\s*\\catcode", "conditional catcode is forbidden"),
    (r"\\csname.*\\endcsname", "csname construction is restricted"),
]


def sanitize_latex(source: str) -> Tuple[bool, str]:
    """Check LaTeX source for dangerous commands.

    Args:
        source: LaTeX source code to check.

    Returns:
        Tuple of (is_safe, error_message).
    """
    if not source:
        return True, ""

    # Check for dangerous patterns
    for pattern, message in DANGEROUS_PATTERNS:
        if re.search(pattern, source, re.IGNORECASE):
            return False, f"Security violation: {message}"

    # Check for suspicious backtick usage (command substitution attempt)
    if "`" in source and re.search(r"`[^`]+`", source):
        # Allow simple backticks for code, but check for shell-like patterns
        if re.search(r"\$\([^)]+\)", source) or re.search(r"\$\{[^}]+\}", source):
            return False, "Security violation: shell substitution pattern detected"

    return True, ""
```

**Step 5: Create `src/execution/security/python_sanitizer.py`**

```python
"""Python code security sanitizer using AST."""

import ast
import re
from typing import Tuple, Set


# Allowed modules for import
ALLOWED_MODULES: Set[str] = {
    "numpy", "np",
    "matplotlib", "matplotlib.pyplot", "plt",
    "matplotlib.patches", "matplotlib.lines",
    "matplotlib.ticker", "matplotlib.colors",
    "pandas", "pd",
    "scipy", "scipy.stats", "scipy.optimize",
    "seaborn", "sns",
    "math", "statistics",
    "json", "re",
    "typing", "dataclasses",
    "collections", "itertools", "functools",
    "datetime", "decimal",
}

# Forbidden function calls
FORBIDDEN_FUNCTIONS: Set[str] = {
    "eval", "exec", "compile",
    "__import__",
    "open",  # File operations should go through sandbox
    "input",
    "breakpoint",
}

# Forbidden module roots
FORBIDDEN_MODULES: Set[str] = {
    "os", "sys", "subprocess", "shutil",
    "socket", "http", "urllib", "requests", "httpx",
    "ctypes", "multiprocessing", "threading",
    "pathlib", "tempfile",
    "importlib", "pkgutil",
    "builtins",
}


def sanitize_python(code: str) -> Tuple[bool, str]:
    """Check Python code for security violations using AST.

    Args:
        code: Python source code to check.

    Returns:
        Tuple of (is_safe, error_message).
    """
    if not code:
        return True, ""

    # First, try to parse the code
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e.msg} at line {e.lineno}"

    # Walk the AST and check for violations
    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    return False, f"Forbidden import: {alias.name}"

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    return False, f"Forbidden import from: {node.module}"
                # Check if in allowed list
                if root not in ALLOWED_MODULES and not any(
                    node.module.startswith(allowed) for allowed in ALLOWED_MODULES
                ):
                    return False, f"Import not in allowlist: {node.module}"

        # Check function calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_FUNCTIONS:
                    return False, f"Forbidden function: {node.func.id}"

            elif isinstance(node.func, ast.Attribute):
                # Check for module.function calls
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id in FORBIDDEN_MODULES:
                        return False, f"Forbidden call: {node.func.value.id}.{node.func.attr}"

    return True, ""
```

**Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/execution/test_sanitizers.py -v`
Expected: PASS (13 tests)

**Step 7: Commit**

```bash
git add src/execution/security/ tests/execution/test_sanitizers.py
git commit -m "feat(execution): add LaTeX and Python security sanitizers"
```

---

## Phase 2: Docker Client

### Task 2.1: Create Docker Client

**Files:**
- Create: `src/execution/docker/__init__.py`
- Create: `src/execution/docker/client.py`
- Create: `tests/execution/test_docker_client.py`

**Step 1: Add docker dependency to pyproject.toml**

Add to `backend/pyproject.toml` dependencies:

```toml
    "docker>=7.0.0",
```

**Step 2: Write the failing test**

Create `tests/execution/test_docker_client.py`:

```python
"""Tests for Docker client wrapper."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.execution.docker.client import DockerClient, DockerExecutionError


class TestDockerClient:
    """Tests for DockerClient."""

    @pytest.fixture
    def mock_docker(self):
        """Mock docker module."""
        with patch("src.execution.docker.client.docker") as mock:
            yield mock

    @pytest.fixture
    def client(self, mock_docker):
        """Create DockerClient instance."""
        return DockerClient()

    def test_client_initialization(self, client):
        """Should initialize without immediate connection."""
        assert client._client is None

    def test_lazy_client_creation(self, client, mock_docker):
        """Should create client lazily."""
        _ = client.client
        mock_docker.from_env.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_image_exists(self, client, mock_docker):
        """Should not pull if image exists."""
        mock_docker.from_env.return_value.images.get.return_value = True

        result = await client.ensure_image("test:latest")

        assert result is True
        mock_docker.from_env.return_value.images.pull.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_image_pulls_if_missing(self, client, mock_docker):
        """Should pull if image doesn't exist."""
        from docker.errors import ImageNotFound
        mock_docker.from_env.return_value.images.get.side_effect = ImageNotFound("test")
        mock_docker.from_env.return_value.images.pull.return_value = None

        result = await client.ensure_image("test:latest")

        assert result is True
        mock_docker.from_env.return_value.images.pull.assert_called_with("test:latest")

    def test_build_volume_mapping(self, client):
        """Should create proper volume mapping."""
        mapping = client.build_volume_mapping("/host/path", "/container/path", "rw")

        assert mapping == {
            "/host/path": {"bind": "/container/path", "mode": "rw"}
        }
```

**Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/execution/test_docker_client.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 4: Create `src/execution/docker/__init__.py`**

```python
"""Docker utilities for execution service."""

from .client import DockerClient, DockerExecutionError

__all__ = ["DockerClient", "DockerExecutionError"]
```

**Step 5: Create `src/execution/docker/client.py`**

```python
"""Docker client wrapper for container execution."""

import asyncio
import logging
from typing import Optional

import docker
from docker.errors import ImageNotFound, APIError, ContainerError

logger = logging.getLogger(__name__)


class DockerExecutionError(Exception):
    """Docker execution error."""
    pass


class DockerClient:
    """Docker client wrapper with async support."""

    def __init__(self, config: Optional[dict] = None):
        """Initialize Docker client.

        Args:
            config: Optional Docker configuration.
        """
        self.config = config or {}
        self._client: Optional[docker.DockerClient] = None

    @property
    def client(self) -> docker.DockerClient:
        """Get or create Docker client lazily."""
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    async def run_container(
        self,
        image: str,
        command: list[str],
        volumes: dict[str, dict],
        timeout: int = 120,
        memory: str = "1g",
        cpu_quota: int = 100000,
        remove: bool = True,
        network_disabled: bool = True,
    ) -> tuple[int, str, str]:
        """Run a container and return results.

        Args:
            image: Docker image name.
            command: Command to run in container.
            volumes: Volume mappings.
            timeout: Execution timeout in seconds.
            memory: Memory limit.
            cpu_quota: CPU quota (100000 = 1 CPU).
            remove: Whether to remove container after execution.
            network_disabled: Whether to disable network.

        Returns:
            Tuple of (exit_code, stdout, stderr).

        Raises:
            DockerExecutionError: If execution fails.
        """
        loop = asyncio.get_event_loop()

        def _run_sync():
            try:
                client = self.client

                # Run container
                container = client.containers.run(
                    image=image,
                    command=command,
                    volumes=volumes,
                    mem_limit=memory,
                    cpu_quota=cpu_quota,
                    remove=False,
                    detach=True,
                    network_disabled=network_disabled,
                )

                # Wait for completion with timeout
                try:
                    result = container.wait(timeout=timeout)
                    exit_code = result.get("StatusCode", -1)
                except Exception as e:
                    container.kill()
                    container.remove()
                    raise DockerExecutionError(f"Container wait failed: {e}")

                # Get logs
                stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
                stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

                # Cleanup
                if remove:
                    container.remove()

                return exit_code, stdout, stderr

            except ContainerError as e:
                return e.exit_status, "", e.stderr.decode() if e.stderr else str(e)
            except ImageNotFound as e:
                raise DockerExecutionError(f"Image not found: {image}")
            except APIError as e:
                raise DockerExecutionError(f"Docker API error: {e}")
            except Exception as e:
                raise DockerExecutionError(f"Unexpected error: {e}")

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, _run_sync),
                timeout=timeout + 10  # Extra buffer for cleanup
            )
        except asyncio.TimeoutError:
            raise DockerExecutionError(f"Container execution timeout after {timeout}s")

    async def ensure_image(self, image: str) -> bool:
        """Ensure Docker image exists, pull if necessary.

        Args:
            image: Docker image name.

        Returns:
            True if image is available.

        Raises:
            DockerExecutionError: If image cannot be obtained.
        """
        loop = asyncio.get_event_loop()

        def _ensure_sync():
            try:
                self.client.images.get(image)
                return True
            except ImageNotFound:
                logger.info(f"Pulling Docker image: {image}")
                self.client.images.pull(image)
                return True
            except Exception as e:
                raise DockerExecutionError(f"Failed to ensure image: {e}")

        try:
            return await loop.run_in_executor(None, _ensure_sync)
        except Exception as e:
            raise DockerExecutionError(f"Image ensure failed: {e}")

    def build_volume_mapping(
        self,
        host_dir: str,
        container_dir: str = "/workspace",
        mode: str = "rw",
    ) -> dict:
        """Build volume mapping for container.

        Args:
            host_dir: Host directory path.
            container_dir: Container mount path.
            mode: Access mode (rw/ro).

        Returns:
            Volume mapping dictionary.
        """
        return {
            host_dir: {"bind": container_dir, "mode": mode}
        }

    async def health_check(self) -> dict:
        """Check Docker daemon health.

        Returns:
            Health status dictionary.
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.client.ping())
            return {"status": "healthy", "docker": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
```

**Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/execution/test_docker_client.py -v`
Expected: PASS (5 tests)

**Step 7: Commit**

```bash
git add src/execution/docker/ tests/execution/test_docker_client.py pyproject.toml
git commit -m "feat(execution): add Docker client wrapper"
```

---

## Phase 3: LaTeX Provider

### Task 3.1: Create LaTeX Provider

**Files:**
- Create: `src/execution/providers/latex.py`
- Update: `src/execution/providers/__init__.py`
- Create: `tests/execution/test_latex_provider.py`

**Step 1: Write the failing test**

Create `tests/execution/test_latex_provider.py`:

```python
"""Tests for LaTeX execution provider."""

import pytest
from pathlib import Path
from src.execution.providers.latex import LaTeXProvider


class TestLaTeXProvider:
    """Tests for LaTeXProvider."""

    @pytest.fixture
    def provider(self):
        """Create LaTeXProvider instance."""
        return LaTeXProvider()

    def test_execution_type(self, provider):
        """Should return correct execution type."""
        assert provider.execution_type == "latex_compile"

    def test_docker_image(self, provider):
        """Should return Docker image name."""
        assert provider.docker_image == "academiagpt/texlive:2024"

    def test_build_command_simple(self, provider):
        """Should build command for simple LaTeX."""
        content = r"\documentclass{article}\begin{document}Hello\end{document}"
        command = provider.build_command(content, {})

        assert "xelatex" in " ".join(command)
        assert "main.tex" in " ".join(command)

    def test_build_command_with_bibtex(self, provider):
        """Should build command chain with BibTeX."""
        content = r"\documentclass{article}\begin{document}Hello\end{document}"
        options = {"bibliography": "@article{test, ...}"}
        command = provider.build_command(content, options)

        cmd_str = " ".join(command)
        assert "bibtex" in cmd_str.lower()

    def test_build_command_uses_pdflatex(self, provider):
        """Should use pdflatex when specified."""
        content = r"\documentclass{article}\begin{document}Hello\end{document}"
        options = {"compiler": "pdflatex"}
        command = provider.build_command(content, options)

        assert "pdflatex" in " ".join(command)

    def test_extract_error_latex_error(self, provider):
        """Should extract LaTeX error message."""
        log = "! LaTeX Error: Environment undefined.\nBlah blah"
        error = provider._extract_error(log)
        assert "LaTeX Error" in error

    def test_extract_error_file_not_found(self, provider):
        """Should extract file not found error."""
        log = "! File `missing.tex' not found"
        error = provider._extract_error(log)
        assert "missing.tex" in error
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/execution/test_latex_provider.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create `src/execution/providers/latex.py`**

```python
"""LaTeX compilation provider."""

import logging
import re
from pathlib import Path
from typing import Optional

from ..base import ExecutionProvider
from ..types import ProviderResult
from ..security.latex_sanitizer import sanitize_latex

logger = logging.getLogger(__name__)


class LaTeXProvider(ExecutionProvider):
    """LaTeX compilation provider using TeXLive."""

    execution_type = "latex_compile"
    docker_image = "academiagpt/texlive:2024"

    def build_command(self, content: str, options: dict) -> list[str]:
        """Build Docker execution command.

        Args:
            content: LaTeX source code.
            options: Compilation options (compiler, bibliography, etc.)

        Returns:
            Command list for Docker execution.
        """
        compiler = options.get("compiler", "xelatex")
        has_bib = options.get("bibliography") is not None

        # Write source file command
        write_source = f"cat > /workspace/main.tex << 'EOF_LATEX'\n{content}\nEOF_LATEX"

        # Write bibliography if provided
        write_bib = ""
        if has_bib:
            bib_content = options["bibliography"]
            write_bib = f" && cat > /workspace/references.bib << 'EOF_BIB'\n{bib_content}\nEOF_BIB"

        # Build compile chain
        compile_cmd = self._build_compile_chain(compiler, has_bib)

        # Combine all commands
        full_cmd = f"{write_source}{write_bib} && {compile_cmd}"

        return ["sh", "-c", full_cmd]

    def _build_compile_chain(self, compiler: str, has_bib: bool) -> str:
        """Build compilation command chain.

        Args:
            compiler: LaTeX compiler (xelatex/pdflatex).
            has_bib: Whether bibliography is present.

        Returns:
            Shell command string.
        """
        base_flags = "-no-shell-escape -interaction=nonstopmode -file-line-error"

        if has_bib:
            # LaTeX -> BibTeX -> LaTeX -> LaTeX
            return (
                f"{compiler} {base_flags} main.tex && "
                f"bibtex main && "
                f"{compiler} {base_flags} main.tex && "
                f"{compiler} {base_flags} main.tex"
            )
        else:
            # Compile up to 3 times for cross-references
            compile_once = f"{compiler} {base_flags} main.tex"
            return f"{compile_once} && {compile_once} && {compile_once}"

    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict,
        docker_client=None,
    ) -> ProviderResult:
        """Execute LaTeX compilation.

        Note: Actual execution happens in Docker via DockerExecutionService.
        This method only performs security validation.

        Args:
            content: LaTeX source code.
            work_dir: Working directory.
            options: Compilation options.
            docker_client: Docker client (unused).

        Returns:
            ProviderResult with security check status.
        """
        # Security check
        is_safe, error = sanitize_latex(content)
        if not is_safe:
            return ProviderResult(
                success=False,
                error_message=f"Security violation: {error}",
            )

        # Actual execution handled by DockerExecutionService
        raise NotImplementedError("Use DockerExecutionService.execute instead")

    async def process_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        work_dir: str,
        options: dict,
    ) -> ProviderResult:
        """Process Docker execution result.

        Args:
            exit_code: Container exit code.
            stdout: Container stdout.
            stderr: Container stderr.
            work_dir: Working directory path.
            options: Compilation options.

        Returns:
            ProviderResult with output files.
        """
        work_path = Path(work_dir)
        pdf_path = work_path / "main.pdf"

        if exit_code == 0 and pdf_path.exists():
            # Get metadata
            metadata = {
                "file_size": pdf_path.stat().st_size,
            }

            # Try to count pages
            page_count = self._count_pages(pdf_path)
            if page_count > 0:
                metadata["page_count"] = page_count

            return ProviderResult(
                success=True,
                output_files=["main.pdf"],
                metadata=metadata,
                logs=self._truncate_log(stdout),
            )
        else:
            error = self._extract_error(stdout + stderr)
            return ProviderResult(
                success=False,
                error_message=error,
                logs=self._truncate_log(stdout + stderr),
            )

    def _extract_error(self, log: str) -> str:
        """Extract meaningful error from LaTeX log.

        Args:
            log: Compilation log.

        Returns:
            Error message string.
        """
        patterns = [
            r"! LaTeX Error: ([^\n]+)",
            r"! File `(.+?)' not found",
            r"! Undefined control sequence",
            r"! Package ([^\n]+) Error",
            r"! (.+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, log, re.DOTALL)
            if match:
                error = match.group(0)
                # Clean up whitespace
                error = re.sub(r"\s+", " ", error)
                return error[:300]  # Limit length

        # Try to find error line context
        context_match = re.search(r"l\.(\d+) (.+)", log)
        if context_match:
            return f"Error at line {context_match.group(1)}: {context_match.group(2)[:200]}"

        return "Unknown LaTeX compilation error"

    def _count_pages(self, pdf_path: Path) -> int:
        """Count PDF pages using PyMuPDF.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            Page count, or 0 if unable to determine.
        """
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0

    def _truncate_log(self, log: str, max_len: int = 2000) -> str:
        """Truncate log to reasonable size.

        Args:
            log: Full log string.
            max_len: Maximum length.

        Returns:
            Truncated log.
        """
        if len(log) <= max_len:
            return log
        return log[-max_len:]
```

**Step 4: Update `src/execution/providers/__init__.py`**

```python
"""Execution providers package."""

from ..base import ExecutionProvider
from .latex import LaTeXProvider

__all__ = ["ExecutionProvider", "LaTeXProvider"]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/execution/test_latex_provider.py -v`
Expected: PASS (7 tests)

**Step 6: Commit**

```bash
git add src/execution/providers/latex.py src/execution/providers/__init__.py tests/execution/test_latex_provider.py
git commit -m "feat(execution): add LaTeX compilation provider"
```

---

### Task 3.2: Create TeXLive Docker Image

**Files:**
- Create: `docker/images/texlive/Dockerfile`

**Step 1: Create Docker images directory**

```bash
mkdir -p docker/images/texlive
```

**Step 2: Create `docker/images/texlive/Dockerfile`**

```dockerfile
# TeXLive Docker image for LaTeX compilation
FROM ubuntu:22.04

LABEL maintainer="AcademiaGPT Team"
LABEL description="TeXLive 2024 for academic paper compilation"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Install TeXLive and essential packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core TeXLive
    texlive-latex-base \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    # Science and bibliography
    texlive-science \
    texlive-bibtex-extra \
    biber \
    # XeLaTeX for Chinese/multilingual support
    texlive-xetex \
    texlive-lang-chinese \
    # Utilities
    ghostscript \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create workspace directory
WORKDIR /workspace

# Default command
ENTRYPOINT ["sh", "-c"]
```

**Step 3: Build the image (optional, for local testing)**

Run: `cd /home/cjz/academiagpt-v2 && docker build -t academiagpt/texlive:2024 -f docker/images/texlive/Dockerfile docker/images/texlive/`

**Step 4: Commit**

```bash
git add docker/images/texlive/Dockerfile
git commit -m "feat(docker): add TeXLive image for LaTeX compilation"
```

---

## Phase 4: Execution Service

### Task 4.1: Create Docker Execution Service

**Files:**
- Create: `src/execution/service.py`
- Update: `src/execution/__init__.py`
- Create: `tests/execution/test_execution_service.py`

**Step 1: Write the failing test**

Create `tests/execution/test_execution_service.py`:

```python
"""Tests for DockerExecutionService."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from src.execution.service import DockerExecutionService
from src.execution.types import ExecutionRequest, ExecutionType, ExecutionStatus


class TestDockerExecutionService:
    """Tests for DockerExecutionService."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory."""
        return str(tmp_path)

    @pytest.fixture
    def service(self, temp_dir):
        """Create DockerExecutionService instance."""
        return DockerExecutionService(sandbox_base_dir=temp_dir)

    def test_provider_map_has_all_types(self, service):
        """Should have providers for all execution types."""
        assert ExecutionType.LATEX_COMPILE in service.PROVIDER_MAP
        # Others will be added in later phases

    @pytest.mark.asyncio
    async def test_health_check(self, service):
        """Should return health status."""
        with patch.object(service.docker_client, 'health_check', new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "healthy"}
            result = await service.health_check()
            assert result["status"] == "healthy"

    def test_prepare_work_dir(self, service, temp_dir):
        """Should create working directory."""
        request = ExecutionRequest(
            execution_type=ExecutionType.LATEX_COMPILE,
            content="test",
            thread_id="test-thread",
        )
        work_dir = service._prepare_work_dir(request)

        assert work_dir.exists()
        assert "test-thread" in str(work_dir)
        assert "latex_compile" in str(work_dir)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/execution/test_execution_service.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create `src/execution/service.py`**

```python
"""Docker-based execution service."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .base import ExecutionService
from .types import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    ProviderResult,
)
from .docker.client import DockerClient, DockerExecutionError
from .providers.latex import LaTeXProvider

logger = logging.getLogger(__name__)


class DockerExecutionService(ExecutionService):
    """Execution service using Docker containers."""

    # Provider registry
    PROVIDER_MAP: dict[ExecutionType, type] = {
        ExecutionType.LATEX_COMPILE: LaTeXProvider,
        # More providers added in later phases:
        # ExecutionType.PYTHON_PLOT: PythonVizProvider,
        # ExecutionType.MERMAID_DIAGRAM: DiagramProvider,
        # ExecutionType.AI_IMAGE: AIImageProvider,
    }

    def __init__(
        self,
        sandbox_base_dir: str,
        docker_config: Optional[dict] = None,
    ):
        """Initialize execution service.

        Args:
            sandbox_base_dir: Base directory for sandbox files.
            docker_config: Optional Docker configuration.
        """
        self.sandbox_base_dir = Path(sandbox_base_dir)
        self.docker_client = DockerClient(docker_config)
        self._providers: dict[ExecutionType, Any] = {}

    def _get_provider(self, exec_type: ExecutionType):
        """Get or create provider instance.

        Args:
            exec_type: Execution type.

        Returns:
            Provider instance.

        Raises:
            ValueError: If execution type is not supported.
        """
        if exec_type not in self._providers:
            provider_cls = self.PROVIDER_MAP.get(exec_type)
            if not provider_cls:
                raise ValueError(f"Unsupported execution type: {exec_type}")
            self._providers[exec_type] = provider_cls()
        return self._providers[exec_type]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a task.

        Args:
            request: Execution request.

        Returns:
            Execution result.
        """
        start_time = time.time()

        try:
            provider = self._get_provider(request.execution_type)

            # Prepare work directory
            work_dir = self._prepare_work_dir(request)

            # Execute based on provider type
            if provider.docker_image:
                # Docker-based execution
                result = await self._execute_in_docker(
                    provider, request, str(work_dir)
                )
            else:
                # Non-Docker execution (e.g., API calls)
                result = await provider.execute(
                    content=request.content,
                    work_dir=str(work_dir),
                    options=request.options,
                )

            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Build result
            if result.success and result.output_files:
                # Convert to sandbox virtual path
                sandbox_path = self._to_sandbox_path(
                    work_dir / result.output_files[0],
                    request.thread_id,
                )

                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    sandbox_path=sandbox_path,
                    execution_time_ms=execution_time_ms,
                    metadata=result.metadata,
                    logs=result.logs,
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error_message=result.error_message or "Execution failed",
                    execution_time_ms=execution_time_ms,
                    logs=result.logs,
                )

        except DockerExecutionError as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
            )

        except ValueError as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
            )

    async def _execute_in_docker(
        self,
        provider: Any,
        request: ExecutionRequest,
        work_dir: str,
    ) -> ProviderResult:
        """Execute task in Docker container.

        Args:
            provider: Execution provider.
            request: Execution request.
            work_dir: Working directory path.

        Returns:
            Provider result.
        """
        # Ensure Docker image is available
        await self.docker_client.ensure_image(provider.docker_image)

        # Build volume mapping
        volumes = self.docker_client.build_volume_mapping(
            host_dir=work_dir,
            container_dir="/workspace",
        )

        # Build command
        command = provider.build_command(request.content, request.options)

        # Run container
        exit_code, stdout, stderr = await self.docker_client.run_container(
            image=provider.docker_image,
            command=command,
            volumes=volumes,
            timeout=request.timeout,
        )

        # Process result
        return await provider.process_result(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            work_dir=work_dir,
            options=request.options,
        )

    def _prepare_work_dir(self, request: ExecutionRequest) -> Path:
        """Prepare working directory for execution.

        Args:
            request: Execution request.

        Returns:
            Working directory path.
        """
        thread_id = request.thread_id or "default"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        work_dir = (
            self.sandbox_base_dir
            / thread_id
            / "execution"
            / request.execution_type.value
            / timestamp
        )
        work_dir.mkdir(parents=True, exist_ok=True)

        return work_dir

    def _to_sandbox_path(self, physical_path: Path, thread_id: Optional[str]) -> str:
        """Convert physical path to sandbox virtual path.

        Args:
            physical_path: Physical file path.
            thread_id: Thread ID.

        Returns:
            Sandbox virtual path (e.g., /mnt/user-data/...).
        """
        thread_id = thread_id or "default"
        relative = physical_path.relative_to(self.sandbox_base_dir / thread_id)
        return f"/mnt/user-data/{relative}"

    async def health_check(self) -> dict:
        """Check service health.

        Returns:
            Health status dictionary.
        """
        docker_health = await self.docker_client.health_check()

        return {
            "status": docker_health.get("status", "unknown"),
            "docker": docker_health,
            "providers": list(self.PROVIDER_MAP.keys()),
        }
```

**Step 4: Update `src/execution/__init__.py`**

```python
"""Execution service for LaTeX, Python, diagram, and AI image generation."""

from .types import (
    ExecutionType,
    ExecutionStatus,
    ExecutionRequest,
    ExecutionResult,
    ProviderResult,
    CompilerType,
    ImageProvider,
)
from .base import ExecutionService, ExecutionProvider
from .service import DockerExecutionService

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
    "DockerExecutionService",
]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/execution/test_execution_service.py -v`
Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add src/execution/service.py src/execution/__init__.py tests/execution/test_execution_service.py
git commit -m "feat(execution): add DockerExecutionService"
```

---

## Phase 5: LaTeX Tool

### Task 5.1: Create compile_latex Tool

**Files:**
- Create: `src/tools/execution/__init__.py`
- Create: `src/tools/execution/compile_latex.py`
- Create: `tests/tools/execution/__init__.py`
- Create: `tests/tools/execution/test_compile_latex.py`

**Step 1: Create directory structure**

```bash
mkdir -p src/tools/execution tests/tools/execution
```

**Step 2: Write the failing test**

Create `tests/tools/execution/test_compile_latex.py`:

```python
"""Tests for compile_latex tool."""

import pytest
from langchain_core.tools import Tool
from src.tools.execution.compile_latex import compile_latex_tool


class TestCompileLatexTool:
    """Tests for compile_latex tool."""

    def test_tool_is_langchain_tool(self):
        """Should be a LangChain tool."""
        from langchain_core.tools import BaseTool
        assert isinstance(compile_latex_tool, BaseTool)

    def test_tool_name(self):
        """Should have correct name."""
        assert compile_latex_tool.name == "compile_latex_tool"

    def test_tool_description(self):
        """Should have descriptive docstring."""
        assert "LaTeX" in compile_latex_tool.description
        assert "PDF" in compile_latex_tool.description

    def test_tool_has_args_schema(self):
        """Should have args schema."""
        assert compile_latex_tool.args_schema is not None

    def test_args_schema_fields(self):
        """Args schema should have expected fields."""
        schema = compile_latex_tool.args_schema.model_json_schema()
        properties = schema.get("properties", {})

        assert "latex_source" in properties
        assert "compiler" in properties
        assert "bibliography" in properties

    def test_compiler_default_is_xelatex(self):
        """Default compiler should be xelatex."""
        schema = compile_latex_tool.args_schema.model_json_schema()
        compiler = schema["properties"]["compiler"]
        assert compiler.get("default") == "xelatex"
```

**Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/tools/execution/test_compile_latex.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 4: Create `src/tools/execution/compile_latex.py`**

```python
"""LaTeX compilation tool."""

from typing import Literal, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class CompileLatexInput(BaseModel):
    """Input schema for compile_latex tool."""

    latex_source: str = Field(
        description="Complete LaTeX source code to compile into PDF"
    )
    compiler: Literal["pdflatex", "xelatex"] = Field(
        default="xelatex",
        description="LaTeX compiler to use. Use xelatex for Chinese or multilingual content."
    )
    bibliography: Optional[str] = Field(
        default=None,
        description="Optional BibTeX bibliography content for references"
    )
    timeout: int = Field(
        default=120,
        ge=30,
        le=600,
        description="Compilation timeout in seconds"
    )


@tool(args_schema=CompileLatexInput)
async def compile_latex_tool(
    latex_source: str,
    compiler: str = "xelatex",
    bibliography: Optional[str] = None,
    timeout: int = 120,
) -> str:
    """Compile LaTeX source code to PDF.

    Use this tool when you have generated complete LaTeX code and need to
    compile it into a PDF document. Supports both pdflatex and xelatex compilers.

    For Chinese content, always use xelatex (the default).

    The tool returns the path to the compiled PDF file, or an error message
    if compilation fails.

    Args:
        latex_source: Complete LaTeX source code including documentclass and
                      all content.
        compiler: LaTeX compiler (pdflatex or xelatex). Default: xelatex.
        bibliography: Optional BibTeX content for references.
        timeout: Compilation timeout in seconds. Default: 120.

    Returns:
        Success message with PDF path, or error message.
    """
    # Actual execution handled by ExecutionMiddleware
    # This returns empty string; real implementation in middleware
    return ""


# Export tool instance
compile_latex = compile_latex_tool
```

**Step 5: Create `src/tools/execution/__init__.py`**

```python
"""Execution tools package."""

from .compile_latex import compile_latex_tool, compile_latex

__all__ = ["compile_latex_tool", "compile_latex"]


def get_execution_tools() -> list:
    """Get all execution tool instances.

    Returns:
        List of LangChain tool instances.
    """
    return [
        compile_latex_tool,
    ]
```

**Step 6: Create `tests/tools/execution/__init__.py`**

```python
"""Tests for execution tools."""
```

**Step 7: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/tools/execution/test_compile_latex.py -v`
Expected: PASS (6 tests)

**Step 8: Commit**

```bash
git add src/tools/execution/ tests/tools/execution/
git commit -m "feat(tools): add compile_latex tool"
```

---

## Phase 6: Execution Middleware

### Task 6.1: Create Execution Middleware

**Files:**
- Create: `src/agents/middlewares/execution.py`
- Update: `src/agents/middlewares/__init__.py`
- Create: `tests/agents/middlewares/test_execution_middleware.py`

**Step 1: Write the failing test**

Create `tests/agents/middlewares/test_execution_middleware.py`:

```python
"""Tests for ExecutionMiddleware."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.agents.middlewares.execution import ExecutionMiddleware
from src.execution.types import ExecutionResult, ExecutionStatus, ExecutionType


class TestExecutionMiddleware:
    """Tests for ExecutionMiddleware."""

    @pytest.fixture
    def mock_service(self):
        """Create mock execution service."""
        service = Mock()
        service.execute = AsyncMock()
        return service

    @pytest.fixture
    def middleware(self, mock_service):
        """Create ExecutionMiddleware instance."""
        return ExecutionMiddleware(execution_service=mock_service)

    def test_execution_tools_list(self, middleware):
        """Should have list of execution tools."""
        assert "compile_latex_tool" in middleware.EXECUTION_TOOLS
        assert middleware.EXECUTION_TOOLS["compile_latex_tool"] == ExecutionType.LATEX_COMPILE

    @pytest.mark.asyncio
    async def test_skips_non_execution_tools(self, middleware):
        """Should not process non-execution tools."""
        result = await middleware.before_tool(
            tool_name="bash_tool",
            tool_args={"command": "ls"},
            config={},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_processes_compile_latex_tool(self, middleware, mock_service):
        """Should process compile_latex_tool."""
        mock_service.execute.return_value = ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            sandbox_path="/mnt/user-data/test.pdf",
            execution_time_ms=1000,
        )

        # after_tool should return the result
        config = {}
        await middleware.before_tool(
            tool_name="compile_latex_tool",
            tool_args={
                "latex_source": "\\documentclass{article}\\begin{doc}test\\end{doc}",
            },
            config=config,
        )

        # The result should be stored for after_tool
        assert "execution_result" in config
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/agents/middlewares/test_execution_middleware.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create `src/agents/middlewares/execution.py`**

```python
"""Execution middleware for handling execution tools."""

import logging
from typing import Any, Optional

from .base import BaseMiddleware
from src.execution.types import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionType,
)

logger = logging.getLogger(__name__)


class ExecutionMiddleware(BaseMiddleware):
    """Middleware for handling execution tool calls.

    Intercepts execution tool calls and routes them through
    the ExecutionService for Docker-based or API-based execution.
    """

    # Mapping of tool names to execution types
    EXECUTION_TOOLS = {
        "compile_latex_tool": ExecutionType.LATEX_COMPILE,
        # More tools added in later phases:
        # "plot_chart_tool": ExecutionType.PYTHON_PLOT,
        # "create_diagram_tool": ExecutionType.MERMAID_DIAGRAM,
        # "generate_image_tool": ExecutionType.AI_IMAGE,
    }

    def __init__(self, execution_service: Any):
        """Initialize middleware.

        Args:
            execution_service: ExecutionService instance.
        """
        self.execution_service = execution_service

    async def before_tool(
        self,
        tool_name: str,
        tool_args: dict,
        config: dict,
    ) -> Optional[tuple[str, dict, dict]]:
        """Process tool before execution.

        Args:
            tool_name: Name of the tool being called.
            tool_args: Tool arguments.
            config: Configuration dict.

        Returns:
            None to continue normal flow, or modified values.
        """
        if tool_name not in self.EXECUTION_TOOLS:
            return None  # Not an execution tool, continue normally

        # Get execution type
        exec_type = self.EXECUTION_TOOLS[tool_name]

        # Extract context
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        workspace_id = configurable.get("workspace_id")

        # Build execution request
        request = self._build_request(
            exec_type=exec_type,
            tool_args=tool_args,
            thread_id=thread_id,
            workspace_id=workspace_id,
        )

        # Execute
        result = await self.execution_service.execute(request)

        # Store result for after_tool
        config["execution_result"] = result

        return None  # Continue to after_tool

    async def after_tool(
        self,
        tool_name: str,
        tool_output: str,
        config: dict,
    ) -> Optional[str]:
        """Process tool output after execution.

        Args:
            tool_name: Name of the tool.
            tool_output: Tool output string.
            config: Configuration dict.

        Returns:
            Modified output or None to keep original.
        """
        if tool_name not in self.EXECUTION_TOOLS:
            return None

        result = config.pop("execution_result", None)
        if result:
            return result.to_tool_output()

        return None

    def _build_request(
        self,
        exec_type: ExecutionType,
        tool_args: dict,
        thread_id: Optional[str],
        workspace_id: Optional[str],
    ) -> ExecutionRequest:
        """Build execution request from tool arguments.

        Args:
            exec_type: Execution type.
            tool_args: Tool arguments.
            thread_id: Thread ID.
            workspace_id: Workspace ID.

        Returns:
            ExecutionRequest instance.
        """
        if exec_type == ExecutionType.LATEX_COMPILE:
            return ExecutionRequest(
                execution_type=exec_type,
                content=tool_args.get("latex_source", ""),
                options={
                    "compiler": tool_args.get("compiler", "xelatex"),
                    "bibliography": tool_args.get("bibliography"),
                },
                timeout=tool_args.get("timeout", 120),
                thread_id=thread_id,
                workspace_id=workspace_id,
            )

        # Other execution types will be added here
        raise ValueError(f"Unsupported execution type: {exec_type}")
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/agents/middlewares/test_execution_middleware.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/agents/middlewares/execution.py tests/agents/middlewares/test_execution_middleware.py
git commit -m "feat(middleware): add ExecutionMiddleware for execution tools"
```

---

## Phase 7: Integration Tests

### Task 7.1: Create Integration Test for LaTeX

**Files:**
- Create: `tests/execution/test_latex_integration.py`

**Step 1: Create integration test**

Create `tests/execution/test_latex_integration.py`:

```python
"""Integration tests for LaTeX execution."""

import pytest
import tempfile
from pathlib import Path

from src.execution import (
    DockerExecutionService,
    ExecutionRequest,
    ExecutionType,
    ExecutionStatus,
)


class TestLaTeXIntegration:
    """Integration tests for LaTeX compilation.

    Note: These tests require Docker to be running and the
    academiagpt/texlive:2024 image to be available.
    """

    @pytest.fixture
    def service(self):
        """Create execution service."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DockerExecutionService(sandbox_base_dir=tmpdir)

    @pytest.fixture
    def simple_latex(self):
        """Simple LaTeX document."""
        return r"""
\documentclass{article}
\begin{document}
Hello, World!
\end{document}
"""

    @pytest.fixture
    def chinese_latex(self):
        """Chinese LaTeX document."""
        return r"""
\documentclass{article}
\usepackage{ctex}
\begin{document}
你好，世界！
\end{document}
"""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not pytest.importorskip("docker", reason="Docker not installed"),
        reason="Docker not available"
    )
    @pytest.mark.integration
    async def test_compile_simple_latex(self, service, simple_latex):
        """Should compile simple LaTeX document."""
        request = ExecutionRequest(
            execution_type=ExecutionType.LATEX_COMPILE,
            content=simple_latex,
            thread_id="test-integration",
            options={"compiler": "pdflatex"},
            timeout=60,
        )

        result = await service.execute(request)

        assert result.status == ExecutionStatus.SUCCESS
        assert result.sandbox_path is not None
        assert result.sandbox_path.endswith(".pdf")
        assert result.metadata.get("file_size", 0) > 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not pytest.importorskip("docker", reason="Docker not installed"),
        reason="Docker not available"
    )
    @pytest.mark.integration
    async def test_compile_chinese_latex(self, service, chinese_latex):
        """Should compile Chinese LaTeX document with xelatex."""
        request = ExecutionRequest(
            execution_type=ExecutionType.LATEX_COMPILE,
            content=chinese_latex,
            thread_id="test-chinese",
            options={"compiler": "xelatex"},
            timeout=120,
        )

        result = await service.execute(request)

        assert result.status == ExecutionStatus.SUCCESS
        assert result.sandbox_path is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_compile_invalid_latex(self, service):
        """Should fail for invalid LaTeX."""
        request = ExecutionRequest(
            execution_type=ExecutionType.LATEX_COMPILE,
            content=r"\invalidcommand",
            thread_id="test-invalid",
            timeout=60,
        )

        result = await service.execute(request)

        assert result.status == ExecutionStatus.FAILED
        assert result.error_message is not None
```

**Step 2: Run integration test (requires Docker)**

Run: `cd backend && python -m pytest tests/execution/test_latex_integration.py -v -m integration`
Expected: PASS (if Docker available) or SKIP (if Docker not available)

**Step 3: Commit**

```bash
git add tests/execution/test_latex_integration.py
git commit -m "test(execution): add LaTeX integration tests"
```

---

## Phase 8: Additional Providers (Skeleton)

### Task 8.1: Create Python Provider Skeleton

**Files:**
- Create: `src/execution/providers/python_viz.py`
- Update: `src/execution/providers/__init__.py`

**Step 1: Create `src/execution/providers/python_viz.py`**

```python
"""Python visualization provider (skeleton)."""

import logging
from pathlib import Path

from ..base import ExecutionProvider
from ..types import ProviderResult

logger = logging.getLogger(__name__)


class PythonVizProvider(ExecutionProvider):
    """Python data visualization provider using matplotlib."""

    execution_type = "python_plot"
    docker_image = "academiagpt/python-viz:1.0"

    def build_command(self, content: str, options: dict) -> list[str]:
        """Build execution command."""
        output_format = options.get("format", "png")
        output_path = f"/workspace/output/chart.{output_format}"

        # Wrap code with matplotlib setup and save
        wrapped_code = f'''
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False

# User code
{content}

# Save figure
import os
os.makedirs('/workspace/output', exist_ok=True)
'''

        return ["python", "-c", wrapped_code]

    async def execute(self, content: str, work_dir: str, options: dict, docker_client=None) -> ProviderResult:
        """Execute Python visualization (handled by Docker)."""
        raise NotImplementedError("Use DockerExecutionService.execute instead")

    async def process_result(self, exit_code: int, stdout: str, stderr: str, work_dir: str, options: dict) -> ProviderResult:
        """Process execution result."""
        work_path = Path(work_dir)
        output_dir = work_path / "output"

        if exit_code == 0 and output_dir.exists():
            images = list(output_dir.glob("*.png")) + list(output_dir.glob("*.svg"))
            if images:
                return ProviderResult(
                    success=True,
                    output_files=[f"output/{img.name}" for img in images],
                    metadata={"format": options.get("format", "png")},
                    logs=stdout,
                )

        return ProviderResult(
            success=False,
            error_message=stderr or "Python execution failed",
            logs=stdout + "\n" + stderr,
        )
```

**Step 2: Update `src/execution/providers/__init__.py`**

```python
"""Execution providers package."""

from ..base import ExecutionProvider
from .latex import LaTeXProvider
from .python_viz import PythonVizProvider

__all__ = ["ExecutionProvider", "LaTeXProvider", "PythonVizProvider"]
```

**Step 3: Commit**

```bash
git add src/execution/providers/python_viz.py src/execution/providers/__init__.py
git commit -m "feat(execution): add Python visualization provider skeleton"
```

---

## Summary

This plan implements the execution service in phases:

1. **Phase 1**: Core types and interfaces
2. **Phase 2**: Docker client
3. **Phase 3**: LaTeX provider and Docker image
4. **Phase 4**: Execution service
5. **Phase 5**: compile_latex tool
6. **Phase 6**: Execution middleware
7. **Phase 7**: Integration tests
8. **Phase 8**: Additional providers (Python, Diagram, AI Image)

Each task follows TDD with:
- Write failing test
- Run test to verify failure
- Implement minimal code
- Run test to verify pass
- Commit

---

*Plan saved to `docs/plans/2026-03-10-execution-service-implementation.md`*
