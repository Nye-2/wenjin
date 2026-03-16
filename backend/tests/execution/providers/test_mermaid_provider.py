"""Tests for MermaidProvider."""

import pytest
from pathlib import Path

from src.execution.providers.mermaid import MermaidProvider
from src.execution.types import ProviderResult


class TestMermaidProviderContract:
    """Test MermaidProvider satisfies the provider contract."""

    def test_execution_type(self):
        provider = MermaidProvider()
        assert provider.execution_type == "mermaid_diagram"

    def test_docker_image(self):
        provider = MermaidProvider()
        assert provider.docker_image is not None
        assert "mermaid" in provider.docker_image.lower()

    def test_build_command_returns_list(self):
        provider = MermaidProvider()
        command = provider.build_command("graph TD; A-->B", {})
        assert isinstance(command, list)
        assert len(command) > 0

    def test_build_command_includes_input_and_output(self):
        provider = MermaidProvider()
        command = provider.build_command("graph TD; A-->B", {})
        cmd_str = " ".join(command)
        assert "input" in cmd_str or "-i" in cmd_str
        assert "output" in cmd_str or "-o" in cmd_str


class TestMermaidProviderProcessResult:
    """Test process_result handles Docker output correctly."""

    @pytest.mark.asyncio
    async def test_success_with_svg_output(self, tmp_path: Path):
        provider = MermaidProvider()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "diagram.svg").write_text("<svg>test</svg>")

        result = await provider.process_result(
            exit_code=0,
            stdout="Done",
            stderr="",
            work_dir=str(tmp_path),
            options={},
        )
        assert result.success is True
        assert result.output_files
        assert any("svg" in f for f in result.output_files)

    @pytest.mark.asyncio
    async def test_success_with_png_output(self, tmp_path: Path):
        provider = MermaidProvider()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "diagram.png").write_bytes(b"\x89PNG")

        result = await provider.process_result(
            exit_code=0,
            stdout="Done",
            stderr="",
            work_dir=str(tmp_path),
            options={"format": "png"},
        )
        assert result.success is True
        assert result.output_files

    @pytest.mark.asyncio
    async def test_failure_on_nonzero_exit(self, tmp_path: Path):
        provider = MermaidProvider()
        result = await provider.process_result(
            exit_code=1,
            stdout="",
            stderr="Parse error",
            work_dir=str(tmp_path),
            options={},
        )
        assert result.success is False
        assert result.error_message

    @pytest.mark.asyncio
    async def test_failure_on_no_output_files(self, tmp_path: Path):
        provider = MermaidProvider()
        (tmp_path / "output").mkdir()
        result = await provider.process_result(
            exit_code=0,
            stdout="",
            stderr="",
            work_dir=str(tmp_path),
            options={},
        )
        assert result.success is False


class TestMermaidProviderRegistration:
    """Test that MermaidProvider is registered in the service."""

    def test_provider_registered_in_service(self):
        from src.execution.service import DockerExecutionService
        from src.execution.types import ExecutionType

        assert ExecutionType.MERMAID_DIAGRAM in DockerExecutionService.PROVIDER_MAP
