"""Runtime helpers for MCP lifecycle activation and shutdown."""

from __future__ import annotations

import logging

from langchain_core.tools import BaseTool

from src.config.extensions_config import ExtensionsConfig
from src.mcp.manager import (
    MCPManager,
    peek_mcp_manager,
    reset_mcp_manager,
    set_mcp_manager,
)

logger = logging.getLogger(__name__)


async def activate_mcp_runtime(
    *,
    config_path: str | None = None,
    extensions_config: ExtensionsConfig | None = None,
    warmup: bool = True,
) -> tuple[MCPManager, list[BaseTool]]:
    """Replace the active MCP runtime and optionally warm tool cache."""
    current_manager = peek_mcp_manager()
    if current_manager is not None:
        await current_manager.close()

    manager = MCPManager(config_path=config_path)
    resolved_config = extensions_config or ExtensionsConfig.from_file(config_path)
    await manager.load_from_extensions_config(resolved_config)

    tools: list[BaseTool] = []
    if warmup and manager.list_servers():
        tools = await manager.load_tools(force_reload=True)
        logger.info(
            "MCP runtime warmed with %s server(s) and %s tool(s)",
            len(manager.list_servers()),
            len(tools),
        )
    else:
        logger.info(
            "MCP runtime activated with %s server(s) and warmup=%s",
            len(manager.list_servers()),
            warmup,
        )

    set_mcp_manager(manager)
    return manager, tools


async def shutdown_mcp_runtime() -> None:
    """Close and clear the active MCP runtime if present."""
    manager = peek_mcp_manager()
    if manager is None:
        return

    await manager.close()
    reset_mcp_manager()
