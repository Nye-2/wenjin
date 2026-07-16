"""Unified extensions configuration for MCP servers and skill state."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.reflection.resolvers import resolve_env_variables


class McpOAuthConfig(BaseModel):
    """OAuth configuration for an MCP server."""

    enabled: bool = Field(default=True)
    token_url: str = Field(default="")
    grant_type: Literal["client_credentials", "refresh_token"] = Field(
        default="client_credentials",
    )
    client_id: str | None = Field(default=None)
    client_secret: str | None = Field(default=None)
    refresh_token: str | None = Field(default=None)
    scope: str | None = Field(default=None)
    audience: str | None = Field(default=None)
    token_field: str = Field(default="access_token")
    token_type_field: str = Field(default="token_type")
    expires_in_field: str = Field(default="expires_in")
    default_token_type: str = Field(default="Bearer")
    refresh_skew_seconds: int = Field(default=60)
    extra_token_params: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class McpServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    name: str | None = Field(default=None)
    enabled: bool = Field(default=True)
    type: Literal["stdio", "sse", "http"] = Field(default="stdio")
    command: str | None = Field(default=None)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = Field(default=None)
    headers: dict[str, str] = Field(default_factory=dict)
    oauth: McpOAuthConfig | None = Field(default=None)
    timeout: int = Field(default=30)
    description: str = Field(default="")

    model_config = ConfigDict(extra="allow")


class ExtensionsConfig(BaseModel):
    """Extensions configuration for MCP servers."""

    mcp_servers: dict[str, McpServerConfig] = Field(
        default_factory=dict,
        alias="mcpServers",
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @classmethod
    def default_config_path(cls) -> Path:
        """Return the preferred extensions config file location."""
        return Path(__file__).resolve().parents[2] / "extensions_config.json"

    @classmethod
    def resolve_config_path(cls, config_path: str | None = None) -> Path | None:
        """Resolve the single authoritative extensions config file path."""
        if config_path:
            explicit_path = Path(config_path).expanduser()
            if not explicit_path.exists():
                raise FileNotFoundError(
                    f"Extensions config file not found at {explicit_path}"
                )
            return explicit_path

        env_var = "WENJIN_EXTENSIONS_CONFIG_PATH"
        env_path = os.getenv(env_var)
        if env_path:
            candidate = Path(env_path).expanduser()
            if not candidate.exists():
                raise FileNotFoundError(
                    f"Extensions config file specified by {env_var} not found at {candidate}"
                )
            return candidate

        default_path = cls.default_config_path()
        return default_path if default_path.exists() else None

    @classmethod
    def from_file(cls, config_path: str | None = None) -> ExtensionsConfig:
        """Load extensions config from JSON file."""
        resolved_path = cls.resolve_config_path(config_path)
        if resolved_path is None:
            return cls()

        with open(resolved_path, encoding="utf-8") as file:
            config_data = json.load(file)

        resolved = resolve_env_variables(config_data)
        return cls.model_validate(resolved)

    def get_enabled_mcp_servers(self) -> dict[str, McpServerConfig]:
        """Return enabled MCP servers only."""
        return {
            name: config
            for name, config in self.mcp_servers.items()
            if config.enabled
        }

_extensions_config: ExtensionsConfig | None = None


def default_config_path() -> Path:
    """Return the preferred extensions config file location."""
    return ExtensionsConfig.default_config_path()


def get_extensions_config() -> ExtensionsConfig:
    """Get cached extensions config."""
    global _extensions_config
    if _extensions_config is None:
        _extensions_config = ExtensionsConfig.from_file()
    return _extensions_config


def reload_extensions_config(config_path: str | None = None) -> ExtensionsConfig:
    """Reload extensions config from disk."""
    global _extensions_config
    _extensions_config = ExtensionsConfig.from_file(config_path)
    return _extensions_config


def reset_extensions_config() -> None:
    """Reset cached extensions config."""
    global _extensions_config
    _extensions_config = None


def set_extensions_config(config: ExtensionsConfig) -> None:
    """Inject a custom extensions config instance."""
    global _extensions_config
    _extensions_config = config
