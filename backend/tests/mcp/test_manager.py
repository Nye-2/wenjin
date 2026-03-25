"""Tests for MCP manager lifecycle and cache behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.config.extensions_config import ExtensionsConfig, McpServerConfig
from src.mcp.manager import (
    MCPManager,
    get_cached_mcp_tools,
    reset_mcp_manager,
    reset_mcp_tools_cache,
    set_mcp_manager,
)


class FakeMCPClient:
    """Fake managed client used by MCP manager tests."""

    def __init__(self, server_name: str, config: McpServerConfig, tools: list[str]):
        self.server_name = server_name
        self.config = config
        self.tools = [SimpleNamespace(name=name) for name in tools]
        self.disconnected = False
        self.force_reload_calls: list[bool] = []

    async def list_tools(self, *, force_reload: bool = False):
        self.force_reload_calls.append(force_reload)
        return list(self.tools)

    async def disconnect(self):
        self.disconnected = True


@pytest.fixture(autouse=True)
def _reset_singletons():
    reset_mcp_manager()
    yield
    reset_mcp_manager()


@pytest.mark.asyncio
async def test_load_from_extensions_config_replaces_servers_and_closes_removed_clients():
    created_clients: dict[str, FakeMCPClient] = {}

    def _client_factory(server_name: str, config: McpServerConfig):
        client = FakeMCPClient(server_name, config, tools=[f"{server_name}_tool"])
        created_clients[server_name] = client
        return client

    manager = MCPManager(client_factory=_client_factory)
    manager.register(McpServerConfig(name="legacy", type="stdio", command="echo"))
    manager.get_client("legacy")

    new_config = ExtensionsConfig(
        mcp_servers={
            "remote": McpServerConfig(enabled=True, type="http", url="https://example.com/mcp")
        }
    )

    await manager.load_from_extensions_config(new_config)

    assert manager.list_servers() == ["remote"]
    assert created_clients["legacy"].disconnected is True


@pytest.mark.asyncio
async def test_load_tools_aggregates_and_dedupes_by_name():
    def _client_factory(server_name: str, config: McpServerConfig):
        tool_sets = {
            "alpha": ["shared_search", "alpha_only"],
            "beta": ["shared_search", "beta_only"],
        }
        return FakeMCPClient(server_name, config, tools=tool_sets[server_name])

    manager = MCPManager(client_factory=_client_factory)
    manager.register(McpServerConfig(name="alpha", type="stdio", command="echo"))
    manager.register(McpServerConfig(name="beta", type="stdio", command="echo"))

    tools = await manager.load_tools()

    assert [tool.name for tool in tools] == [
        "shared_search",
        "alpha_only",
        "beta_only",
    ]
    assert [tool.name for tool in manager.list_tools()] == [
        "shared_search",
        "alpha_only",
        "beta_only",
    ]


@pytest.mark.asyncio
async def test_load_tools_tracks_server_failures():
    class BrokenClient(FakeMCPClient):
        async def list_tools(self, *, force_reload: bool = False):
            raise RuntimeError(f"{self.server_name} unavailable")

    def _client_factory(server_name: str, config: McpServerConfig):
        return BrokenClient(server_name, config, tools=[])

    manager = MCPManager(client_factory=_client_factory)
    manager.register(McpServerConfig(name="alpha", type="stdio", command="echo"))

    tools = await manager.load_tools()

    assert tools == []
    assert manager.get_last_load_errors() == {"alpha": "alpha unavailable"}


def test_get_cached_mcp_tools_uses_singleton_manager():
    manager = MCPManager(
        client_factory=lambda server_name, config: FakeMCPClient(
            server_name,
            config,
            tools=[f"{server_name}_tool"],
        )
    )
    manager.register(McpServerConfig(name="cache-test", type="stdio", command="echo"))
    set_mcp_manager(manager)
    reset_mcp_tools_cache()

    tools = get_cached_mcp_tools()

    assert [tool.name for tool in tools] == ["cache-test_tool"]
