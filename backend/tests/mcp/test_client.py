"""Tests for MCP client integration."""

import pytest
from src.mcp.client import MCPClient, MCPServerConfig


class TestMCPServerConfig:
    def test_create_config(self):
        """Should create MCP server configuration."""
        config = MCPServerConfig(
            name="test-server",
            command="python",
            args=["-m", "test_server"],
        )
        assert config.name == "test-server"
        assert config.command == "python"
        assert config.args == ["-m", "test_server"]

    def test_config_with_env(self):
        """Should support environment variables."""
        config = MCPServerConfig(
            name="test-server",
            command="python",
            args=[],
            env={"API_KEY": "test"},
        )
        assert config.env == {"API_KEY": "test"}


class TestMCPClient:
    @pytest.mark.asyncio
    async def test_client_initialize(self):
        """Client should initialize."""
        client = MCPClient()
        assert client is not None

    @pytest.mark.asyncio
    async def test_client_not_connected_initially(self):
        """Client should not be connected initially."""
        client = MCPClient()
        assert not client.is_connected

    def test_create_from_config(self):
        """Should create client from config."""
        config = MCPServerConfig(name="test", command="echo", args=[])
        client = MCPClient(config)
        assert client.config == config


class TestMCPManager:
    def test_manager_creation(self):
        """Manager should be created."""
        from src.mcp.manager import MCPManager
        manager = MCPManager()
        assert manager is not None

    def test_list_tools_empty(self):
        """Should return empty list if no servers."""
        from src.mcp.manager import MCPManager
        manager = MCPManager()
        tools = manager.list_tools()
        assert isinstance(tools, list)
        assert len(tools) == 0

    def test_register_server(self):
        """Should register a server config."""
        from src.mcp.manager import MCPManager
        manager = MCPManager()
        config = MCPServerConfig(name="test", command="echo", args=[])
        manager.register(config)
        assert "test" in manager.list_servers()
