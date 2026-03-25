"""Tests for extensions configuration loading."""

from __future__ import annotations

import json

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
                "skills": {
                    "deep-research": {"enabled": False},
                },
            }
        ),
        encoding="utf-8",
    )

    config = ExtensionsConfig.from_file(str(config_path))

    assert config.mcp_servers["remote"].env["API_KEY"] == "secret-key"
    assert config.skills["deep-research"].enabled is False


def test_extensions_config_skill_default_behavior():
    config = ExtensionsConfig()

    assert config.is_skill_enabled("deep-research", "public") is True
    assert config.is_skill_enabled("internal-worker", "private") is False


def test_extensions_config_cache_helpers_reload_from_disk(tmp_path, monkeypatch):
    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {}, "skills": {"deep-research": {"enabled": True}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("ACADEMIAGPT_EXTENSIONS_CONFIG_PATH", str(config_path))
    reset_extensions_config()

    cached = get_extensions_config()
    assert cached.skills["deep-research"].enabled is True

    config_path.write_text(
        json.dumps({"mcpServers": {}, "skills": {"deep-research": {"enabled": False}}}),
        encoding="utf-8",
    )

    reloaded = reload_extensions_config()
    assert reloaded.skills["deep-research"].enabled is False


def test_extensions_config_ignores_legacy_deer_flow_env(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy_extensions.json"
    legacy_path.write_text(json.dumps({"mcpServers": {"legacy": {"enabled": True, "type": "stdio", "command": "echo"}}}), encoding="utf-8")

    monkeypatch.delenv("ACADEMIAGPT_EXTENSIONS_CONFIG_PATH", raising=False)
    monkeypatch.setenv("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(legacy_path))

    resolved = ExtensionsConfig.resolve_config_path()

    assert resolved == ExtensionsConfig.default_config_path()
