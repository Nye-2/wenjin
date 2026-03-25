"""MCP client helpers and single-server wrapper."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool

from src.config.extensions_config import ExtensionsConfig, McpServerConfig
from src.mcp.oauth import OAuthTokenManager, wrap_tool_with_oauth

logger = logging.getLogger(__name__)

MCPServerConfig = McpServerConfig
MultiServerClientFactory = Callable[[dict[str, dict[str, Any]]], Any]


def build_server_params(server_name: str, config: MCPServerConfig) -> dict[str, Any]:
    """Build adapter parameters for a single MCP server."""
    transport_type = config.type or "stdio"
    adapter_transport = "streamable_http" if transport_type == "http" else transport_type
    params: dict[str, Any] = {"transport": adapter_transport}

    if transport_type == "stdio":
        if not config.command:
            raise ValueError(
                f"MCP server '{server_name}' with stdio transport requires 'command' field"
            )
        params["command"] = config.command
        params["args"] = list(config.args)
        if config.env:
            params["env"] = dict(config.env)
        return params

    if transport_type in ("sse", "http"):
        if not config.url:
            raise ValueError(
                f"MCP server '{server_name}' with {transport_type} transport requires 'url' field"
            )
        params["url"] = config.url
        if config.headers:
            params["headers"] = dict(config.headers)
        return params

    raise ValueError(
        f"MCP server '{server_name}' has unsupported transport type: {transport_type}"
    )


def build_servers_config(
    extensions_config: ExtensionsConfig,
) -> dict[str, dict[str, Any]]:
    """Build adapter configuration for all enabled MCP servers."""
    servers_config: dict[str, dict[str, Any]] = {}

    for server_name, server_config in extensions_config.get_enabled_mcp_servers().items():
        try:
            servers_config[server_name] = build_server_params(server_name, server_config)
        except Exception as exc:
            logger.error("Failed to configure MCP server '%s': %s", server_name, exc)

    return servers_config


def _default_client_factory(servers_config: dict[str, dict[str, Any]]) -> Any:
    """Instantiate the langchain MCP adapter client."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    return MultiServerMCPClient(servers_config)


class MCPClient:
    """Wrapper around a single MCP server connection."""

    def __init__(
        self,
        config: MCPServerConfig | None = None,
        *,
        server_name: str | None = None,
        client_factory: MultiServerClientFactory | None = None,
        oauth_token_manager: OAuthTokenManager | None = None,
    ) -> None:
        self._config = config
        self._server_name = server_name or getattr(config, "name", None) or "default"
        self._client_factory = client_factory or _default_client_factory
        self._oauth_token_manager = oauth_token_manager
        self._client: Any | None = None
        self._server_params: dict[str, Any] | None = None
        self._connected = False
        self._tools_cache: list[BaseTool] | None = None

        if self._oauth_token_manager is None and config is not None:
            self._oauth_token_manager = OAuthTokenManager.from_server_configs(
                {self._server_name: config}
            )

    @property
    def config(self) -> MCPServerConfig | None:
        """Get the server configuration."""
        return self._config

    @property
    def server_name(self) -> str:
        """Get the logical server name."""
        return self._server_name

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._connected

    async def connect(self) -> None:
        """Connect to the MCP server."""
        if self._connected and self._client is not None:
            return
        if self._config is None:
            raise ValueError("No server configuration provided")

        server_params = build_server_params(self._server_name, self._config)
        if self._oauth_token_manager is not None:
            await self._oauth_token_manager.apply_authorization(
                self._server_name,
                server_params,
            )

        self._server_params = server_params
        self._client = self._client_factory({self._server_name: self._server_params})
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._client is not None:
            close_method = getattr(self._client, "aclose", None)
            if callable(close_method):
                await close_method()
            else:
                close_method = getattr(self._client, "close", None)
                if callable(close_method):
                    result = close_method()
                    if inspect.isawaitable(result):
                        await result
        self._client = None
        self._server_params = None
        self._connected = False
        self._tools_cache = None

    async def list_tools(self, *, force_reload: bool = False) -> list[BaseTool]:
        """List tools exposed by the MCP server."""
        if not self._connected or self._client is None:
            await self.connect()

        if self._tools_cache is not None and not force_reload:
            return list(self._tools_cache)

        if self._client is None:
            return []

        if self._server_params is not None and self._oauth_token_manager is not None:
            await self._oauth_token_manager.apply_authorization(
                self._server_name,
                self._server_params,
            )

        tools = await self._client.get_tools()
        loaded_tools = list(tools or [])
        if self._server_params is not None:
            loaded_tools = [
                wrap_tool_with_oauth(
                    tool,
                    server_name=self._server_name,
                    connection=self._server_params,
                    token_manager=self._oauth_token_manager,
                )
                for tool in loaded_tools
            ]

        self._tools_cache = loaded_tools
        return list(self._tools_cache)
