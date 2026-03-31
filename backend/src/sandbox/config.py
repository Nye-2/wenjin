# src/sandbox/config.py
"""Sandbox configuration using Pydantic Settings."""

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocalSandboxConfig(BaseModel):
    """Local sandbox configuration."""

    base_dir: str = Field(
        default=".wenjin/threads",
        description="Base directory for thread data",
    )


class DockerSandboxConfig(BaseModel):
    """Docker sandbox configuration."""

    image: str = Field(
        default="wenjin/sandbox:latest",
        description="Docker image for sandbox",
    )
    timeout: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Default command timeout in seconds",
    )
    memory: str = Field(
        default="1g",
        description="Memory limit for container",
    )
    cpu_limit: int = Field(
        default=2,
        ge=1,
        description="CPU limit for container",
    )


class LaTeXConfig(BaseModel):
    """LaTeX compilation configuration."""

    enabled: bool = Field(default=True, description="Enable LaTeX compilation")
    engine: Literal["xelatex", "pdflatex"] = Field(
        default="xelatex",
        description="LaTeX engine to use",
    )


class CodeExecutionConfig(BaseModel):
    """Code execution configuration."""

    enabled: bool = Field(default=True, description="Enable code execution")
    languages: list[str] = Field(
        default=["python", "r"],
        description="Supported languages",
    )


class AcademicToolsConfig(BaseModel):
    """Academic tools configuration."""

    latex: LaTeXConfig = Field(default_factory=LaTeXConfig)
    code_execution: CodeExecutionConfig = Field(default_factory=CodeExecutionConfig)


class SandboxSettings(BaseSettings):
    """Sandbox system configuration."""

    model_config = SettingsConfigDict(
        env_prefix="SANDBOX_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    mode: Literal["local", "docker"] = Field(
        default="local",
        description="Sandbox mode: local or docker",
    )

    local: LocalSandboxConfig = Field(default_factory=LocalSandboxConfig)
    docker: DockerSandboxConfig = Field(default_factory=DockerSandboxConfig)
    academic: AcademicToolsConfig = Field(default_factory=AcademicToolsConfig)

    # Global settings
    default_timeout: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Default command timeout in seconds",
    )
    max_timeout: int = Field(
        default=900,
        ge=60,
        le=7200,
        description="Maximum allowed timeout",
    )


# Convenience function
def get_sandbox_settings() -> SandboxSettings:
    """Get sandbox settings instance."""
    return SandboxSettings()
