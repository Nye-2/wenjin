"""MCP configuration router."""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.config import ExtensionsConfig, get_extensions_config, reload_extensions_config
from src.database import User
from src.gateway.routers.auth import get_current_user
from src.mcp import MCPManager, activate_mcp_runtime

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_admin(current_user: User) -> None:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")


class McpOAuthConfigResponse(BaseModel):
    """OAuth configuration for an MCP server."""

    enabled: bool = Field(default=True)
    token_url: str = Field(default="")
    grant_type: Literal["client_credentials", "refresh_token"] = Field(
        default="client_credentials",
    )
    client_id: str | None = Field(default=None)
    client_secret: str | None = Field(default=None)
    refresh_token: str | None = Field(default=None)
    scope: str | None = Field(default=None)
    audience: str | None = Field(default=None)
    token_field: str = Field(default="access_token")
    token_type_field: str = Field(default="token_type")
    expires_in_field: str = Field(default="expires_in")
    default_token_type: str = Field(default="Bearer")
    refresh_skew_seconds: int = Field(default=60)
    extra_token_params: dict[str, str] = Field(default_factory=dict)


class McpServerConfigResponse(BaseModel):
    """MCP server configuration payload."""

    enabled: bool = Field(default=True)
    type: Literal["stdio", "sse", "http"] = Field(default="stdio")
    command: str | None = Field(default=None)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = Field(default=None)
    headers: dict[str, str] = Field(default_factory=dict)
    oauth: McpOAuthConfigResponse | None = Field(default=None)
    timeout: int = Field(default=30)
    description: str = Field(default="")


class McpConfigResponse(BaseModel):
    """Response model for MCP configuration."""

    mcp_servers: dict[str, McpServerConfigResponse] = Field(default_factory=dict)


class McpConfigUpdateRequest(BaseModel):
    """Request model for updating MCP configuration."""

    mcp_servers: dict[str, McpServerConfigResponse] = Field(default_factory=dict)


def _serialize_mcp_servers(config: ExtensionsConfig) -> dict[str, McpServerConfigResponse]:
    return {
        name: McpServerConfigResponse(**server.model_dump())
        for name, server in config.mcp_servers.items()
    }


@router.get("/mcp/config", response_model=McpConfigResponse)
async def get_mcp_configuration(
    current_user: User = Depends(get_current_user),
) -> McpConfigResponse:
    """Return current MCP configuration."""
    _require_admin(current_user)
    config = get_extensions_config()
    return McpConfigResponse(mcp_servers=_serialize_mcp_servers(config))


@router.put("/mcp/config", response_model=McpConfigResponse)
async def update_mcp_configuration(
    request: McpConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> McpConfigResponse:
    """Persist MCP server configuration and refresh runtime state."""
    _require_admin(current_user)
    try:
        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            config_path = ExtensionsConfig.default_config_path()

        current_config = get_extensions_config()
        config_data = current_config.model_dump(by_alias=True, exclude_none=True)
        config_data["mcpServers"] = {
            name: server.model_dump(exclude_none=True)
            for name, server in request.mcp_servers.items()
        }
        candidate_config = ExtensionsConfig.model_validate(config_data)

        validation_manager = MCPManager(config_path=str(config_path))
        try:
            await validation_manager.load_from_extensions_config(candidate_config)
            await validation_manager.load_tools(force_reload=True)
            runtime_errors = validation_manager.get_last_load_errors()
        finally:
            await validation_manager.close()

        if runtime_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "MCP runtime validation failed for one or more servers",
                    "errors": runtime_errors,
                },
            )

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as file:
            json.dump(
                candidate_config.model_dump(by_alias=True, exclude_none=True),
                file,
                indent=2,
                ensure_ascii=False,
            )

        reloaded_config = reload_extensions_config(str(config_path))
        await activate_mcp_runtime(
            config_path=str(config_path),
            extensions_config=reloaded_config,
            warmup=True,
        )
        return McpConfigResponse(mcp_servers=_serialize_mcp_servers(reloaded_config))
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.error("Failed to update MCP configuration: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update MCP configuration: {exc}",
        ) from exc
