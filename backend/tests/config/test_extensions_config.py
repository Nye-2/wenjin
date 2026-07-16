"""Tests for extensions configuration loading."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.config.extensions_config import (
    ExtensionsConfig,
    get_extensions_config,
    reload_extensions_config,
    reset_extensions_config,
)


def test_extensions_config_from_file_resolves_env_variables(tmp_path, monkeypatch):
    config_path = tmp_path / "extensions_config.json"
    monkeypatch.setenv("MCP_API_KEY", "secret-key")
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote": {
                        "enabled": True,
                        "type": "stdio",
                        "command": "npx",
                        "env": {"API_KEY": "$MCP_API_KEY"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    config = ExtensionsConfig.from_file(str(config_path))

    assert config.mcp_servers["remote"].env["API_KEY"] == "secret-key"


def test_extensions_config_rejects_obsolete_thread_skills():
    with pytest.raises(ValidationError, match="skills"):
        ExtensionsConfig.model_validate({"mcpServers": {}, "skills": {"old": {}}})


def test_extensions_config_cache_helpers_reload_from_disk(tmp_path, monkeypatch):
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WENJIN_EXTENSIONS_CONFIG_PATH", str(config_path))
    reset_extensions_config()

    cached = get_extensions_config()
    assert cached.mcp_servers == {}

    config_path.write_text(
        json.dumps({"mcpServers": {"local": {"type": "stdio", "command": "echo"}}}),
        encoding="utf-8",
    )

    reloaded = reload_extensions_config()
    assert reloaded.mcp_servers["local"].command == "echo"


def test_extensions_config_ignores_legacy_env_vars(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy_extensions.json"
    legacy_path.write_text(json.dumps({"mcpServers": {"legacy": {"enabled": True, "type": "stdio", "command": "echo"}}}), encoding="utf-8")

    monkeypatch.delenv("WENJIN_EXTENSIONS_CONFIG_PATH", raising=False)
    monkeypatch.setenv("ACADEMIAGPT_EXTENSIONS_CONFIG_PATH", str(legacy_path))
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(legacy_path))

    resolved = ExtensionsConfig.resolve_config_path()

    assert resolved == ExtensionsConfig.default_config_path()
