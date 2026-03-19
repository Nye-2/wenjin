"""Integration tests for LaTeX execution."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from src.execution import (
    DockerExecutionService,
    ExecutionRequest,
    ExecutionStatus,
    ExecutionType,
)

_DEFAULT_LATEX_IMAGE = "academiagpt/texlive:2024"
_LATEX_IMAGE = os.getenv("ACADEMIAGPT_TEXLIVE_IMAGE", _DEFAULT_LATEX_IMAGE)


def check_docker_available():
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_latex_runtime_available() -> bool:
    """Check whether the LaTeX runtime is locally available without network pulls."""
    if not check_docker_available():
        return False

    try:
        result = subprocess.run(
            ["docker", "image", "inspect", _LATEX_IMAGE],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

    if _LATEX_IMAGE != _DEFAULT_LATEX_IMAGE:
        return False

    candidates: list[Path] = []

    env_specific = os.getenv("ACADEMIAGPT_TEXLIVE_IMAGE_TAR")
    if env_specific:
        candidates.append(Path(env_specific).expanduser())

    env_generic = os.getenv("DOCKER_IMAGE_TAR_PATH")
    if env_generic:
        candidates.append(Path(env_generic).expanduser())

    backend_root = Path(__file__).resolve().parents[2]
    candidates.append(
        backend_root / "docker" / "images" / "texlive" / "academiagpt-texlive-2024.tar"
    )
    candidates.append(
        Path("/opt/academiagpt/images/texlive/academiagpt-texlive-2024.tar")
    )

    return any(path.is_file() for path in candidates)


_LATEX_RUNTIME_AVAILABLE = check_latex_runtime_available()


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
        "not _LATEX_RUNTIME_AVAILABLE",
        reason="LaTeX runtime image/archive not available locally",
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
        "not _LATEX_RUNTIME_AVAILABLE",
        reason="LaTeX runtime image/archive not available locally",
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
    @pytest.mark.skipif(
        "not _LATEX_RUNTIME_AVAILABLE",
        reason="LaTeX runtime image/archive not available locally",
    )
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
