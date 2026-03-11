"""Integration tests for LaTeX execution."""

import pytest
import subprocess
import tempfile
from pathlib import Path

from src.execution import (
    DockerExecutionService,
    ExecutionRequest,
    ExecutionType,
    ExecutionStatus,
)


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


# Pre-compute docker availability for skipif decorator
_DOCKER_AVAILABLE = check_docker_available()


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
    @pytest.mark.skipif("not _DOCKER_AVAILABLE", reason="Docker not available")
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
    @pytest.mark.skipif("not _DOCKER_AVAILABLE", reason="Docker not available")
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
    @pytest.mark.skipif("not _DOCKER_AVAILABLE", reason="Docker not available")
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
