"""LangGraph entrypoints with strict signatures required by langgraph-api."""

import asyncio
import atexit
import logging
import threading
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.lead_agent.agent import make_lead_agent
from src.config import get_extensions_config
from src.mcp import activate_mcp_runtime, shutdown_mcp_runtime

logger = logging.getLogger(__name__)

_bootstrapped = False
_bootstrap_lock = threading.Lock()


def _shutdown_langgraph_runtime() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(shutdown_mcp_runtime())
        except Exception:
            logger.debug("LangGraph MCP runtime shutdown skipped", exc_info=True)


def _ensure_bootstrapped() -> None:
    """Lazily bootstrap MCP runtime on first request."""
    global _bootstrapped
    if _bootstrapped:
        return

    with _bootstrap_lock:
        if _bootstrapped:
            return

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

            _bootstrapped = True
            atexit.register(_shutdown_langgraph_runtime)
            return

        logger.warning(
            "Skipping synchronous MCP bootstrap because an event loop is already running"
        )
        _bootstrapped = True
        atexit.register(_shutdown_langgraph_runtime)


def make_lead_agent_graph(config: RunnableConfig) -> Any:
    """Create the lead agent graph with langgraph-api compatible signature."""
    _ensure_bootstrapped()
    return make_lead_agent(config)
