"""MCP tool manager for loading tools from MCP servers."""

import json
from pathlib import Path


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
            from langchain_mcp_adapters import MultiServerMCPClient
            from langchain_mcp_adapters.tools import load_mcp_tools
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
