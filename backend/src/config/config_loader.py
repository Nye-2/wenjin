"""Unified config.yaml loader for Wenjin."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.reflection.resolvers import resolve_env_variables


class ToolConfig(BaseModel):
    """Tool configuration."""
    name: str = ""
    use: str  # import path for a non-Mission integration hook
    group: str = ""

    def model_post_init(self, __context: object) -> None:
        """Derive name from ``use`` path when not explicitly set."""
        if not self.name and self.use:
            # "package.module:tool" -> "tool"
            self.name = self.use.rsplit(":", 1)[-1] if ":" in self.use else self.use


class ToolGroupConfig(BaseModel):
    """Tool group configuration."""
    name: str = ""
    description: str = ""


class MemoryConfig(BaseModel):
    """Persistent memory configuration."""
    enabled: bool = False
    injection_enabled: bool = True
    debounce_seconds: int = 30
    model_name: str | None = None
    max_facts: int = 100
    fact_confidence_threshold: float = 0.7
    max_injection_tokens: int = 2000
    max_context_turns: int = 3
    similarity_weight: float = 0.6
    confidence_weight: float = 0.4


class TitleConfig(BaseModel):
    """Auto-title generation configuration."""
    enabled: bool = True
    max_words: int = 8
    max_chars: int = 60


class SummarizationConfig(BaseModel):
    """Context summarization configuration."""
    enabled: bool = False
    trigger: str = "tokens:80000"
    keep: str = "messages:10"
    model_name: str | None = None


class AcademicMiddlewareConfig(BaseModel):
    """Academic middleware toggles."""
    workspace_context: bool = True
    literature_context: bool = True
    knowledge_context: bool = True
    discipline_context: bool = True
    citation_tracking: bool = True


class LLMErrorHandlingConfig(BaseModel):
    """LLM error handling middleware toggles."""

    enabled: bool = True


class MiddlewaresConfig(BaseModel):
    """Middleware configuration."""
    summarization: SummarizationConfig = Field(default_factory=SummarizationConfig)
    title: TitleConfig = Field(default_factory=TitleConfig)
    academic: AcademicMiddlewareConfig = Field(default_factory=AcademicMiddlewareConfig)
    llm_error_handling: LLMErrorHandlingConfig = Field(default_factory=LLMErrorHandlingConfig)


class CircuitBreakerConfig(BaseModel):
    """LLM circuit breaker configuration."""

    failure_threshold: int = 5
    recovery_timeout_sec: int = 60


class DatabaseConfig(BaseModel):
    """Database configuration."""
    url: str = ""
    echo: bool = False


class RedisConfig(BaseModel):
    """Redis configuration."""
    url: str = ""


class ThreadBillingConfig(BaseModel):
    """Thread token billing configuration."""

    enabled: bool = True
    free_tokens: int = 100000
    tokens_per_credit: int = 10000
    max_overdraft_credits: int = 100


class MissionBillingConfig(BaseModel):
    """Mission token billing configuration."""

    enabled: bool = True
    free_tokens: int = 0
    tokens_per_credit: int = 10000
    max_overdraft_credits: int = 100


class SandboxBillingConfig(BaseModel):
    """Sandbox operation credit billing configuration."""

    enabled: bool = True
    run_python_credits: int = 1
    max_overdraft_credits: int = 100


class BillingConfig(BaseModel):
    """Billing configuration."""

    thread: ThreadBillingConfig = Field(default_factory=ThreadBillingConfig)
    mission: MissionBillingConfig = Field(default_factory=MissionBillingConfig)
    sandbox: SandboxBillingConfig = Field(default_factory=SandboxBillingConfig)


class AppConfig(BaseModel):
    """Unified application configuration loaded from config.yaml."""
    model_config = ConfigDict(extra="forbid")

    tools: list[ToolConfig] = Field(default_factory=list)
    tool_groups: list[ToolGroupConfig] = Field(default_factory=list)

    @field_validator("tool_groups", mode="before")
    @classmethod
    def _coerce_tool_groups(cls, v: object) -> list[dict[str, Any]]:
        """Accept ``tool_groups`` as either a list or a name→attrs dict."""
        if isinstance(v, dict):
            return [{"name": k, **(val if isinstance(val, dict) else {})} for k, val in v.items()]
        return v  # type: ignore[return-value]
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    middlewares: MiddlewaresConfig = Field(default_factory=MiddlewaresConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    billing: BillingConfig = Field(default_factory=BillingConfig)

    def get_tool_config(self, name: str) -> ToolConfig | None:
        """Find a tool by name."""
        for t in self.tools:
            if t.name == name:
                return t
        return None


def _resolve_config_path(config_path: str | None = None) -> Path | None:
    """Resolve config file path with priority."""
    if config_path:
        p = Path(config_path)
        return p if p.exists() else None

    env_path = os.getenv("WENJIN_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    for candidate in [Path("config.yaml"), Path("../config.yaml")]:
        if candidate.exists():
            return candidate

    return None


def load_config(config_path: str | None = None) -> AppConfig:
    """Load and parse config.yaml with env var resolution.

    Args:
        config_path: Explicit path to config file

    Returns:
        Parsed AppConfig (or defaults if no config found)
    """
    path = _resolve_config_path(config_path)
    if path is None:
        return AppConfig()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    resolved = resolve_env_variables(raw)
    return AppConfig(**resolved)


_app_config: AppConfig | None = None


def get_app_config() -> AppConfig:
    """Get cached singleton config."""
    global _app_config
    if _app_config is None:
        _app_config = load_config()
    return _app_config


def reload_app_config(config_path: str | None = None) -> AppConfig:
    """Force reload config."""
    global _app_config
    _app_config = load_config(config_path)
    return _app_config


def reset_app_config() -> None:
    """Clear cached config."""
    global _app_config
    _app_config = None
