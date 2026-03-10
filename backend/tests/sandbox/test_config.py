# tests/sandbox/test_config.py
"""Tests for sandbox configuration."""

import pytest
from src.sandbox.config import SandboxSettings, AcademicToolsConfig


class TestSandboxSettings:
    def test_default_settings(self):
        """Should have sensible defaults."""
        settings = SandboxSettings()
        assert settings.mode == "local"
        assert settings.local.base_dir == ".academiagpt/threads"

    def test_docker_settings(self):
        """Should support Docker mode."""
        settings = SandboxSettings(
            mode="docker",
            docker={
                "image": "academiagpt/sandbox:latest",
                "timeout": 300,
            },
        )
        assert settings.mode == "docker"

    def test_academic_tools_config(self):
        """Should configure academic tools."""
        settings = SandboxSettings()
        assert settings.academic.latex.enabled is True
        assert settings.academic.code_execution.enabled is True


class TestAcademicToolsConfig:
    def test_latex_config(self):
        """Should configure LaTeX."""
        config = AcademicToolsConfig()
        assert config.latex.enabled is True
        assert config.latex.engine == "xelatex"

    def test_code_execution_config(self):
        """Should configure code execution."""
        config = AcademicToolsConfig()
        assert "python" in config.code_execution.languages
