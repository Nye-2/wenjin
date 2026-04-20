"""Tests for MCP client helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.tools import StructuredTool

from src.config.extensions_config import ExtensionsConfig, McpServerConfig
from src.mcp.client import MCPClient, build_server_params, build_servers_config


class FakeAdapterClient:
    """Small fake adapter client for MCP client tests."""

    def __init__(self, servers_config: dict[str, dict]):
        self.servers_config = servers_config
        self.closed = False
        self.tools = [SimpleNamespace(name="remote_search")]

    async def get_tools(self):
        return list(self.tools)

    async def aclose(self):
        self.closed = True


def test_build_server_params_stdio_success():
    config = McpServerConfig(
        type="stdio",
        command="npx",
        args=["-y", "my-mcp-server"],
        env={"API_KEY": "secret"},
    )

    params = build_server_params("my-server", config)

    assert params == {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "my-mcp-server"],
        "env": {"API_KEY": "secret"},
    }


def test_build_server_params_sse_success():
    config = McpServerConfig(
        type="sse",
        url="https://example.com/mcp",
        headers={"Authorization": "Bearer token"},
    )

    params = build_server_params("remote-server", config)

    assert params == {
        "transport": "sse",
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer token"},
    }


def test_build_server_params_http_uses_streamable_http_transport():
    config = McpServerConfig(
        type="http",
        url="https://example.com/mcp",
        headers={"Authorization": "Bearer token"},
    )

    params = build_server_params("remote-server", config)

    assert params == {
        "transport": "streamable_http",
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer token"},
    }


def test_build_server_params_requires_valid_fields():
    with pytest.raises(ValueError, match="requires 'command' field"):
        build_server_params("broken-stdio", McpServerConfig(type="stdio", command=None))

    with pytest.raises(ValueError, match="requires 'url' field"):
        build_server_params("broken-http", McpServerConfig(type="http", url=None))


def test_build_servers_config_filters_disabled_and_invalid_servers():
    extensions = ExtensionsConfig(
        mcp_servers={
            "valid": McpServerConfig(enabled=True, type="stdio", command="npx"),
            "disabled": McpServerConfig(enabled=False, type="stdio", command="echo"),
            "invalid": McpServerConfig(enabled=True, type="http", url=None),
        }
    )

    result = build_servers_config(extensions)

    assert list(result) == ["valid"]
    assert result["valid"]["transport"] == "stdio"


class TestMCPClient:
    @pytest.mark.asyncio
    async def test_client_not_connected_initially(self):
        client = MCPClient()
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_client_connect_list_tools_and_disconnect(self):
        created_clients: list[FakeAdapterClient] = []

        def _factory(servers_config: dict[str, dict]):
            adapter = FakeAdapterClient(servers_config)
            created_clients.append(adapter)
            return adapter

        config = McpServerConfig(name="test-server", type="stdio", command="python")
        client = MCPClient(config=config, server_name="test-server", client_factory=_factory)

        tools = await client.list_tools()

        assert client.is_connected is True
        assert [tool.name for tool in tools] == ["remote_search"]
        assert created_clients[0].servers_config == {
            "test-server": {
                "transport": "stdio",
                "command": "python",
                "args": [],
            }
        }

        await client.disconnect()
        assert client.is_connected is False
        assert created_clients[0].closed is True

    @pytest.mark.asyncio
    async def test_client_reuses_cached_tools(self):
        created_clients: list[FakeAdapterClient] = []

        def _factory(servers_config: dict[str, dict]):
            adapter = FakeAdapterClient(servers_config)
            created_clients.append(adapter)
            return adapter

        config = McpServerConfig(name="test-server", type="stdio", command="python")
        client = MCPClient(config=config, server_name="test-server", client_factory=_factory)

        await client.list_tools()
        await client.list_tools()

        assert len(created_clients) == 1

    @pytest.mark.asyncio
    async def test_client_refreshes_oauth_headers_for_tool_calls(self):
        class FakeOAuthTokenManager:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def has_oauth_for_server(self, server_name: str) -> bool:
                return server_name == "secure-server"

            async def apply_authorization(
                self,
                server_name: str,
                connection: dict[str, object],
            ) -> bool:
                header = f"Bearer token-{len(self.calls) + 1}"
                headers = dict(connection.get("headers") or {})
                headers["Authorization"] = header
                connection["headers"] = headers
                self.calls.append(header)
                return True

        class OAuthAwareFakeAdapterClient(FakeAdapterClient):
            def __init__(self, servers_config: dict[str, dict]):
                super().__init__(servers_config)
                self.invocation_headers: list[str | None] = []
                connection = servers_config["secure-server"]

                async def _call_tool(**kwargs):
                    self.invocation_headers.append(
                        (connection.get("headers") or {}).get("Authorization")
                    )
                    return ("ok", None)

                self.tools = [
                    StructuredTool(
                        name="secure_search",
                        description="",
                        args_schema={"type": "object", "properties": {}},
                        coroutine=_call_tool,
                        response_format="content_and_artifact",
                    )
                ]

        created_clients: list[OAuthAwareFakeAdapterClient] = []

        def _factory(servers_config: dict[str, dict]):
            adapter = OAuthAwareFakeAdapterClient(servers_config)
            created_clients.append(adapter)
            return adapter

        token_manager = FakeOAuthTokenManager()
        client = MCPClient(
            config=McpServerConfig(
                name="secure-server",
                type="http",
                url="https://example.com/mcp",
            ),
            server_name="secure-server",
            client_factory=_factory,
            oauth_token_manager=token_manager,
        )

        tools = await client.list_tools()
        coroutine = tools[0].coroutine

        assert coroutine is not None
        await coroutine()

        assert created_clients[0].servers_config["secure-server"]["transport"] == (
            "streamable_http"
        )
        assert token_manager.calls == ["Bearer token-1", "Bearer token-2", "Bearer token-3"]
        assert created_clients[0].invocation_headers == ["Bearer token-3"]
