"""Tests for MCP runtime activation helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.config.extensions_config import ExtensionsConfig
from src.mcp import runtime as runtime_module


@pytest.mark.asyncio
async def test_activate_mcp_runtime_replaces_existing_manager(monkeypatch):
    closed: list[bool] = []
    assigned: list[object] = []

    class ExistingManager:
        async def close(self):
            closed.append(True)

    class FakeManager:
        def __init__(self, config_path: str | None = None):
            self.config_path = config_path
            self.loaded_config = None
            self.load_tools_calls: list[bool] = []

        async def load_from_extensions_config(self, extensions_config=None):
            self.loaded_config = extensions_config

        async def load_tools(self, *, force_reload: bool = False):
            self.load_tools_calls.append(force_reload)
            return [SimpleNamespace(name="remote_search")]

        def list_servers(self):
            return ["remote"]

    monkeypatch.setattr(runtime_module, "peek_mcp_manager", lambda: ExistingManager())
    monkeypatch.setattr(runtime_module, "MCPManager", FakeManager)
    monkeypatch.setattr(runtime_module, "set_mcp_manager", assigned.append)

    config = ExtensionsConfig.model_validate(
        {
            "mcpServers": {
                "remote": {
                    "enabled": True,
                    "type": "stdio",
                    "command": "echo",
                }
            }
        }
    )

    manager, tools = await runtime_module.activate_mcp_runtime(
        config_path="/tmp/extensions_config.json",
        extensions_config=config,
        warmup=True,
    )

    assert closed == [True]
    assert manager.loaded_config == config
    assert manager.load_tools_calls == [True]
    assert [tool.name for tool in tools] == ["remote_search"]
    assert assigned == [manager]


@pytest.mark.asyncio
async def test_shutdown_mcp_runtime_closes_and_resets(monkeypatch):
    closed: list[bool] = []
    reset_calls: list[bool] = []

    class ExistingManager:
        async def close(self):
            closed.append(True)

    monkeypatch.setattr(runtime_module, "peek_mcp_manager", lambda: ExistingManager())
    monkeypatch.setattr(runtime_module, "reset_mcp_manager", lambda: reset_calls.append(True))

    await runtime_module.shutdown_mcp_runtime()

    assert closed == [True]
    assert reset_calls == [True]
