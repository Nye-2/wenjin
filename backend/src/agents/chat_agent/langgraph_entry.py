"""LangGraph CLI / Studio entry point for the chat agent.

Used only by the optional ``langgraph`` compose profile (see
``docker-compose.yml`` and ``docs/current/deployment-runbook.md``).
The production gateway process imports :func:`make_chat_agent` directly via
``thread_turn_handler``; this module is *not* on the hot path.

Provides ``make_chat_agent_graph`` — the symbol referenced by
``backend/langgraph.json`` — which returns the underlying compiled LangGraph
suitable for ``langgraph dev`` inspection.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agents.chat_agent.agent import make_chat_agent


def make_chat_agent_graph(config: RunnableConfig | None = None) -> Any:
    """Return the compiled LangGraph for the chat agent.

    LangGraph CLI passes its own ``RunnableConfig`` at runtime; when called
    without one we use an empty configurable so the agent can still be
    introspected by Studio without a live workspace context.
    """
    if config is None:
        config = {"configurable": {"model_name": "mimo-v2.5-pro"}}
    wrapped = make_chat_agent(config)
    # ``_MiddlewareWrappedAgent`` is a thin wrapper around the compiled
    # ``create_react_agent`` graph; expose the inner graph so LangGraph
    # tooling can render the node structure.
    return wrapped._agent
