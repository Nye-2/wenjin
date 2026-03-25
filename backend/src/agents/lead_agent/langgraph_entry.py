"""LangGraph entrypoints with strict signatures required by langgraph-api."""

import asyncio
import atexit
import logging

from langchain_core.runnables import RunnableConfig

from src.agents.lead_agent.agent import make_lead_agent
from src.config import get_extensions_config
from src.mcp import activate_mcp_runtime, shutdown_mcp_runtime

logger = logging.getLogger(__name__)


def _bootstrap_langgraph_runtime() -> None:
    """Warm MCP runtime inside the langgraph process before first request."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(
                activate_mcp_runtime(
                    extensions_config=get_extensions_config(),
                    warmup=True,
                )
            )
        except Exception as exc:
            logger.warning("LangGraph MCP runtime bootstrap skipped: %s", exc, exc_info=True)
        return

    logger.warning(
        "Skipping synchronous MCP bootstrap because an event loop is already running"
    )


def _shutdown_langgraph_runtime() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(shutdown_mcp_runtime())
        except Exception:
            logger.debug("LangGraph MCP runtime shutdown skipped", exc_info=True)


_bootstrap_langgraph_runtime()
atexit.register(_shutdown_langgraph_runtime)


def make_lead_agent_graph(config: RunnableConfig):
    """Create the lead agent graph with langgraph-api compatible signature."""
    return make_lead_agent(config)
