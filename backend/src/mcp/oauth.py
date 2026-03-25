"""OAuth token management and tool wrapping for MCP HTTP/SSE servers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from src.config.extensions_config import ExtensionsConfig, McpOAuthConfig, McpServerConfig

logger = logging.getLogger(__name__)


@dataclass
class _OAuthToken:
    """Cached OAuth access token."""

    access_token: str
    token_type: str
    expires_at: datetime


class OAuthTokenManager:
    """Acquire, cache, and refresh OAuth tokens for MCP servers."""

    def __init__(self, oauth_by_server: dict[str, McpOAuthConfig]):
        self._oauth_by_server = oauth_by_server
        self._tokens: dict[str, _OAuthToken] = {}
        self._locks: dict[str, asyncio.Lock] = {
            name: asyncio.Lock()
            for name in oauth_by_server
        }

    @classmethod
    def from_extensions_config(
        cls,
        extensions_config: ExtensionsConfig,
    ) -> OAuthTokenManager:
        """Build a token manager from enabled servers in extensions config."""
        return cls.from_server_configs(extensions_config.get_enabled_mcp_servers())

    @classmethod
    def from_server_configs(
        cls,
        server_configs: dict[str, McpServerConfig],
    ) -> OAuthTokenManager:
        """Build a token manager from server configs keyed by server name."""
        oauth_by_server: dict[str, McpOAuthConfig] = {}
        for server_name, server_config in server_configs.items():
            oauth = server_config.oauth
            if oauth and oauth.enabled:
                oauth_by_server[server_name] = oauth
        return cls(oauth_by_server)

    def has_oauth_servers(self) -> bool:
        """Return whether any server requires OAuth."""
        return bool(self._oauth_by_server)

    def has_oauth_for_server(self, server_name: str) -> bool:
        """Return whether a server requires OAuth header injection."""
        return server_name in self._oauth_by_server

    def oauth_server_names(self) -> list[str]:
        """Return OAuth-enabled server names."""
        return list(self._oauth_by_server.keys())

    async def get_authorization_header(self, server_name: str) -> str | None:
        """Return a valid Authorization header for a server."""
        oauth = self._oauth_by_server.get(server_name)
        if oauth is None:
            return None

        token = self._tokens.get(server_name)
        if token and not self._is_expiring(token, oauth):
            return f"{token.token_type} {token.access_token}"

        lock = self._locks[server_name]
        async with lock:
            token = self._tokens.get(server_name)
            if token and not self._is_expiring(token, oauth):
                return f"{token.token_type} {token.access_token}"

            fresh_token = await self._fetch_token(oauth)
            self._tokens[server_name] = fresh_token
            logger.info(
                "Refreshed OAuth access token for MCP server '%s'",
                server_name,
            )
            return f"{fresh_token.token_type} {fresh_token.access_token}"

    async def apply_authorization(
        self,
        server_name: str,
        connection: dict[str, Any],
    ) -> bool:
        """Inject or refresh Authorization header for a server connection."""
        header = await self.get_authorization_header(server_name)
        if not header:
            return False

        headers = dict(connection.get("headers") or {})
        headers["Authorization"] = header
        connection["headers"] = headers
        return True

    @staticmethod
    def _is_expiring(token: _OAuthToken, oauth: McpOAuthConfig) -> bool:
        now = datetime.now(UTC)
        return token.expires_at <= now + timedelta(
            seconds=max(oauth.refresh_skew_seconds, 0)
        )

    async def _fetch_token(self, oauth: McpOAuthConfig) -> _OAuthToken:
        import httpx  # pyright: ignore[reportMissingImports]

        data: dict[str, str] = {
            "grant_type": oauth.grant_type,
            **oauth.extra_token_params,
        }

        if oauth.scope:
            data["scope"] = oauth.scope
        if oauth.audience:
            data["audience"] = oauth.audience

        if oauth.grant_type == "client_credentials":
            if not oauth.client_id or not oauth.client_secret:
                raise ValueError(
                    "OAuth client_credentials requires client_id and client_secret"
                )
            data["client_id"] = oauth.client_id
            data["client_secret"] = oauth.client_secret
        elif oauth.grant_type == "refresh_token":
            if not oauth.refresh_token:
                raise ValueError(
                    "OAuth refresh_token grant requires refresh_token"
                )
            data["refresh_token"] = oauth.refresh_token
            if oauth.client_id:
                data["client_id"] = oauth.client_id
            if oauth.client_secret:
                data["client_secret"] = oauth.client_secret
        else:
            raise ValueError(f"Unsupported OAuth grant type: {oauth.grant_type}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(oauth.token_url, data=data)
            response.raise_for_status()
            payload = response.json()

        access_token = payload.get(oauth.token_field)
        if not access_token:
            raise ValueError(
                f"OAuth token response missing '{oauth.token_field}'"
            )

        token_type = str(
            payload.get(oauth.token_type_field, oauth.default_token_type)
            or oauth.default_token_type
        )

        expires_in_raw = payload.get(oauth.expires_in_field, 3600)
        try:
            expires_in = int(expires_in_raw)
        except (TypeError, ValueError):
            expires_in = 3600

        expires_at = datetime.now(UTC) + timedelta(seconds=max(expires_in, 1))
        return _OAuthToken(
            access_token=access_token,
            token_type=token_type,
            expires_at=expires_at,
        )


async def get_initial_oauth_headers(
    extensions_config: ExtensionsConfig,
) -> dict[str, str]:
    """Get Authorization headers for OAuth-enabled servers."""
    token_manager = OAuthTokenManager.from_extensions_config(extensions_config)
    if not token_manager.has_oauth_servers():
        return {}

    headers: dict[str, str] = {}
    for server_name in token_manager.oauth_server_names():
        header = await token_manager.get_authorization_header(server_name)
        if header:
            headers[server_name] = header
    return headers


def wrap_tool_with_oauth(
    tool: BaseTool,
    *,
    server_name: str,
    connection: dict[str, Any],
    token_manager: OAuthTokenManager | None,
) -> BaseTool:
    """Wrap a loaded MCP tool so OAuth headers refresh before each call."""
    if token_manager is None or not token_manager.has_oauth_for_server(server_name):
        return tool

    if not isinstance(tool, StructuredTool) or not callable(tool.coroutine):
        return tool

    original_coroutine = tool.coroutine
    metadata = dict(tool.metadata or {})
    if metadata.get("mcp_oauth_wrapped"):
        return tool

    async def wrapped_coroutine(*args: Any, **kwargs: Any) -> Any:
        await token_manager.apply_authorization(server_name, connection)
        return await original_coroutine(*args, **kwargs)

    metadata["mcp_server_name"] = server_name
    metadata["mcp_oauth_wrapped"] = True

    return tool.model_copy(
        update={
            "coroutine": wrapped_coroutine,
            "metadata": metadata,
        }
    )
