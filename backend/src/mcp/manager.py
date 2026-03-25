"""MCP tool manager for configuration, lifecycle, and cached tool loading."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from pathlib import Path

from langchain_core.tools import BaseTool

from src.config.extensions_config import ExtensionsConfig
from src.mcp.client import MCPClient, MCPServerConfig

logger = logging.getLogger(__name__)

ManagedClientFactory = Callable[[str, MCPServerConfig], MCPClient]


def _dedupe_tools(tools: list[BaseTool]) -> list[BaseTool]:
    """Deduplicate tools by name while preserving order."""
    deduped: list[BaseTool] = []
    seen_names: set[str] = set()

    for tool in tools:
        tool_name = getattr(tool, "name", "")
        if tool_name and tool_name in seen_names:
            continue
        if tool_name:
            seen_names.add(tool_name)
        deduped.append(tool)

    return deduped


class MCPManager:
    """Manage MCP server configuration, client lifecycle, and tool caching."""

    def __init__(
        self,
        config_path: str | None = None,
        *,
        client_factory: ManagedClientFactory | None = None,
    ) -> None:
        self._config_path = config_path
        self._client_factory = client_factory
        self._servers: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, MCPClient] = {}
        self._tools_cache: list[BaseTool] = []
        self._cache_initialized = False
        self._config_mtime: float | None = None
        self._last_load_errors: dict[str, str] = {}

    @property
    def config_path(self) -> str | None:
        """Return the configured extensions config path."""
        return self._config_path

    @property
    def cache_initialized(self) -> bool:
        """Return whether tool cache has been initialized."""
        return self._cache_initialized

    def register(self, config: MCPServerConfig) -> None:
        """Register an MCP server configuration manually."""
        server_name = config.name
        if not server_name:
            raise ValueError("MCP server config requires 'name' when registering manually")

        self._servers[server_name] = config.model_copy(deep=True)
        self._clients.pop(server_name, None)
        self.invalidate_cache()

    async def unregister(self, name: str) -> bool:
        """Unregister an MCP server and disconnect any active client."""
        removed = name in self._servers
        self._servers.pop(name, None)

        client = self._clients.pop(name, None)
        if client is not None:
            await client.disconnect()

        if removed:
            self.invalidate_cache()
        return removed

    def list_servers(self) -> list[str]:
        """List all configured server names."""
        return list(self._servers.keys())

    def list_tools(self) -> list[BaseTool]:
        """Return the cached tools without triggering reload."""
        return list(self._tools_cache)

    def get_client(self, name: str) -> MCPClient | None:
        """Get or create the client for a registered server."""
        config = self._servers.get(name)
        if config is None:
            return None

        client = self._clients.get(name)
        if client is None:
            if self._client_factory is not None:
                client = self._client_factory(name, config)
            else:
                client = MCPClient(config=config, server_name=name)
            self._clients[name] = client

        return client

    def invalidate_cache(self) -> None:
        """Invalidate cached tool list."""
        self._tools_cache = []
        self._cache_initialized = False
        self._last_load_errors = {}

    def get_last_load_errors(self) -> dict[str, str]:
        """Return the most recent per-server tool load failures."""
        return dict(self._last_load_errors)

    def _resolve_config_path(self) -> Path | None:
        return ExtensionsConfig.resolve_config_path(self._config_path)

    def _get_config_mtime(self) -> float | None:
        config_path = self._resolve_config_path()
        if config_path is None or not config_path.exists():
            return None
        return os.path.getmtime(config_path)

    def is_config_stale(self) -> bool:
        """Return whether cached tools are stale versus config file mtime."""
        if not self._cache_initialized:
            return False

        current_mtime = self._get_config_mtime()
        if self._config_mtime is None or current_mtime is None:
            return False

        return current_mtime > self._config_mtime

    async def load_from_extensions_config(
        self,
        extensions_config: ExtensionsConfig | None = None,
    ) -> ExtensionsConfig:
        """Load MCP server definitions from extensions config."""
        loaded_config = extensions_config or ExtensionsConfig.from_file(self._config_path)
        next_servers = {
            name: config.model_copy(deep=True)
            for name, config in loaded_config.get_enabled_mcp_servers().items()
        }

        stale_client_names: set[str] = set(self._clients) - set(next_servers)
        for server_name, server_config in next_servers.items():
            if self._servers.get(server_name) != server_config:
                stale_client_names.add(server_name)

        for server_name in stale_client_names:
            client = self._clients.pop(server_name, None)
            if client is not None:
                await client.disconnect()

        self._servers = next_servers
        self.invalidate_cache()
        self._config_mtime = self._get_config_mtime()
        return loaded_config

    async def load_tools(self, *, force_reload: bool = False) -> list[BaseTool]:
        """Load tools from all configured MCP servers."""
        should_reload_servers = (
            self.is_config_stale()
            or (not self._servers and not self._cache_initialized)
            or (force_reload and not self._servers)
        )
        if should_reload_servers:
            await self.load_from_extensions_config()

        if self._cache_initialized and not force_reload:
            return self.list_tools()

        loaded_tools: list[BaseTool] = []
        load_errors: dict[str, str] = {}
        for server_name in self.list_servers():
            client = self.get_client(server_name)
            if client is None:
                continue

            try:
                tools = await client.list_tools(force_reload=force_reload)
                loaded_tools.extend(tools)
            except ImportError:
                message = (
                    "langchain-mcp-adapters not installed. MCP tools will be unavailable."
                )
                logger.warning(message)
                load_errors[server_name] = message
            except Exception as exc:
                logger.error(
                    "Failed to load MCP tools from server '%s': %s",
                    server_name,
                    exc,
                )
                load_errors[server_name] = str(exc)

        self._tools_cache = _dedupe_tools(loaded_tools)
        self._cache_initialized = True
        self._config_mtime = self._get_config_mtime()
        self._last_load_errors = load_errors
        return self.list_tools()

    async def close(self) -> None:
        """Disconnect all active MCP clients and clear caches."""
        for client in list(self._clients.values()):
            await client.disconnect()
        self._clients.clear()
        self._servers.clear()
        self.invalidate_cache()
        self._config_mtime = None


_mcp_manager: MCPManager | None = None
_initialization_lock = asyncio.Lock()


def get_mcp_manager(config_path: str | None = None) -> MCPManager:
    """Get the cached MCP manager singleton."""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager(config_path=config_path)
    elif config_path is not None and _mcp_manager.config_path != config_path:
        _mcp_manager = MCPManager(config_path=config_path)
    return _mcp_manager


def peek_mcp_manager() -> MCPManager | None:
    """Return the current MCP manager singleton without creating one."""
    return _mcp_manager


def set_mcp_manager(manager: MCPManager) -> None:
    """Inject a custom MCP manager."""
    global _mcp_manager
    _mcp_manager = manager


def reset_mcp_manager() -> None:
    """Reset the cached MCP manager."""
    global _mcp_manager
    _mcp_manager = None


async def initialize_mcp_tools(
    config_path: str | None = None,
    *,
    force_reload: bool = False,
) -> list[BaseTool]:
    """Initialize and cache MCP tools asynchronously."""
    async with _initialization_lock:
        manager = get_mcp_manager(config_path)
        return await manager.load_tools(force_reload=force_reload)


def get_cached_mcp_tools(config_path: str | None = None) -> list[BaseTool]:
    """Get cached MCP tools with lazy initialization and stale-config detection."""
    manager = get_mcp_manager(config_path)
    if manager.cache_initialized and not manager.is_config_stale():
        return manager.list_tools()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    initialize_mcp_tools(config_path, force_reload=True),
                )
                return future.result()

        return loop.run_until_complete(
            initialize_mcp_tools(config_path, force_reload=True)
        )
    except RuntimeError:
        return asyncio.run(initialize_mcp_tools(config_path, force_reload=True))
    except Exception as exc:
        logger.error("Failed to initialize cached MCP tools: %s", exc)
        return []


def reset_mcp_tools_cache() -> None:
    """Reset cached MCP tools on the current singleton manager."""
    manager = _mcp_manager
    if manager is not None:
        manager.invalidate_cache()
