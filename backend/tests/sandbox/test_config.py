"""Tests for sandbox configuration."""

import pytest
from src.sandbox.config import (
    SandboxSettings,
    LocalSandboxConfig,
    DockerSandboxConfig,
    AcademicToolsConfig,
    LaTeXConfig,
    CodeExecutionConfig,
)


class TestLocalSandboxConfig:
    def test_default_base_dir(self):
        """Should have default base directory."""
        config = LocalSandboxConfig()
        assert config.base_dir == ".academiagpt/threads"

    def test_custom_base_dir(self):
        """Should accept custom base directory."""
        config = LocalSandboxConfig(base_dir="/custom/path")
        assert config.base_dir == "/custom/path"


class TestDockerSandboxConfig:
    def test_default_image(self):
        """Should have default Docker image."""
        config = DockerSandboxConfig()
        assert "academiagpt" in config.image

    def test_default_timeout(self):
        """Should have default timeout."""
        config = DockerSandboxConfig()
        assert config.timeout == 300

    def test_custom_settings(self):
        """Should accept custom settings."""
        config = DockerSandboxConfig(
            image="custom/sandbox:v1",
            timeout=600,
            memory="4g",
            cpu_limit=4,
        )
        assert config.image == "custom/sandbox:v1"
        assert config.timeout == 600
        assert config.memory == "4g"
        assert config.cpu_limit == 4


class TestLaTeXConfig:
    def test_default_enabled(self):
        """Should enable LaTeX by default."""
        config = LaTeXConfig()
        assert config.enabled is True

    def test_default_engine(self):
        """Should use xelatex as default engine."""
        config = LaTeXConfig()
        assert config.engine == "xelatex"


class TestCodeExecutionConfig:
    def test_default_enabled(self):
        """Should enable code execution by default."""
        config = CodeExecutionConfig()
        assert config.enabled is True

    def test_default_languages(self):
        """Should support python and r by default."""
        config = CodeExecutionConfig()
        assert "python" in config.languages
        assert "r" in config.languages


class TestAcademicToolsConfig:
    def test_default_latex(self):
        """Should have default LaTeX config."""
        config = AcademicToolsConfig()
        assert config.latex.enabled is True

    def test_default_code_execution(self):
        """Should have default code execution config."""
        config = AcademicToolsConfig()
        assert config.code_execution.enabled is True


class TestSandboxSettings:
    def test_default_mode(self):
        """Should use local mode by default."""
        settings = SandboxSettings()
        assert settings.mode == "local"

    def test_default_timeout(self):
        """Should have default timeout settings."""
        settings = SandboxSettings()
        assert settings.default_timeout == 300
        assert settings.max_timeout == 900

    def test_local_config(self):
        """Should have local config."""
        settings = SandboxSettings()
        assert settings.local is not None
        assert settings.local.base_dir == ".academiagpt/threads"

    def test_docker_config(self):
        """Should have docker config."""
        settings = SandboxSettings()
        assert settings.docker is not None

    def test_academic_config(self):
        """Should have academic tools config."""
        settings = SandboxSettings()
        assert settings.academic is not None
        assert settings.academic.latex.enabled is True

    def test_docker_mode(self):
        """Should support docker mode."""
        settings = SandboxSettings(mode="docker")
        assert settings.mode == "docker"