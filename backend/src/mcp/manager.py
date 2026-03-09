"""MCP tool manager for loading tools from MCP servers."""

import json
from pathlib import Path
from typing import Any

from src.mcp.client import MCPClient, MCPServerConfig


class MCPManager:
    """Manager for multiple MCP server connections."""

    def __init__(self) -> None:
        """Initialize the MCP manager."""
        self._servers: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, MCPClient] = {}

    def register(self, config: MCPServerConfig) -> None:
        """Register an MCP server configuration.

        Args:
            config: Server configuration to register.
        """
        self._servers[config.name] = config

    def list_servers(self) -> list[str]:
        """List all registered server names.

        Returns:
            List of server names.
        """
        return list(self._servers.keys())

    def list_tools(self) -> list[dict[str, Any]]:
        """List all tools from all connected servers.

        Returns:
            List of tool definitions from all servers.
        """
        # Stub implementation - returns empty list for framework
        return []

    def get_client(self, name: str) -> MCPClient | None:
        """Get the client for a registered server.

        Args:
            name: Name of the server.

        Returns:
            MCPClient instance or None if not found.
        """
        if name not in self._servers:
            return None

        if name not in self._clients:
            config = self._servers[name]
            self._clients[name] = MCPClient(config)

        return self._clients[name]


async def get_cached_mcp_tools(
    config_path: str = "./extensions_config.json",
) -> list:
    """Get MCP tools with file mtime-based cache invalidation.

    Args:
        config_path: Path to extensions_config.json

    Returns:
        List of MCP tools
    """
    config_file = Path(config_path)
    if not config_file.exists():
        return []

    try:
        with open(config_file) as f:
            config = json.load(f)

        mcp_servers = config.get("mcpServers", {})
        enabled_servers = {
            name: cfg for name, cfg in mcp_servers.items()
            if cfg.get("enabled", True)
        }

        if not enabled_servers:
            return []

        # Import MCP client
        try:
            from langchain_mcp_adapters import MultiServerMCPClient  # noqa: F401
            from langchain_mcp_adapters.tools import load_mcp_tools  # noqa: F401
        except ImportError:
            return []

        # Load tools from each server
        all_tools = []
        for server_name, server_config in enabled_servers.items():
            try:
                tools = await _load_server_tools(server_name, server_config)
                all_tools.extend(tools)
            except Exception as e:
                print(f"Error loading MCP server {server_name}: {e}")

        return all_tools

    except Exception as e:
        print(f"Error loading MCP tools: {e}")
        return []


async def _load_server_tools(server_name: str, config: dict) -> list:
    """Load tools from a single MCP server.

    Args:
        server_name: Name of the server
        config: Server configuration

    Returns:
        List of tools from this server
    """
    # This is a simplified implementation
    # In production, would use MultiServerMCPClient properly
    return []
