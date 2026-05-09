"""Chat agent factory — builds a LangGraph create_react_agent for a workspace."""

from __future__ import annotations

import logging

from .deps import ChatAgentDeps
from .prompts import get_system_prompt
from .tools import (
    make_cancel_run,
    make_dispatch_capability,
    make_query_run_progress,
    make_read_decisions,
    make_read_documents_meta,
    make_read_library_meta,
    make_read_memory,
    make_read_run_history,
    make_write_decision,
)

logger = logging.getLogger(__name__)


def create_chat_agent(
    deps: ChatAgentDeps,
    *,
    capability_list_text: str = "(待注入)",
    decisions_text: str = "(无)",
    memory_text: str = "(无)",
):
    """Build a chat agent for a specific workspace type, with tools bound to deps.

    The returned agent is a LangGraph CompiledGraph (create_react_agent).
    If deps.langchain_chat_model is None the graph is not built (useful in tests
    that only need the tool layer).

    Args:
        deps: ChatAgentDeps with all service dependencies.
        capability_list_text: Human-readable capability list for the system prompt.
        decisions_text: Current decisions text for the system prompt.
        memory_text: Memory facts text for the system prompt.

    Returns:
        A LangGraph CompiledGraph, or None if no langchain_chat_model is provided.
    """
    system_prompt = get_system_prompt(
        deps.workspace_type,
        capability_list=capability_list_text,
        decisions=decisions_text,
        memory_facts=memory_text,
    )

    tools = [
        make_dispatch_capability(deps),
        make_query_run_progress(deps),
        make_cancel_run(deps),
        make_write_decision(deps),
        make_read_decisions(deps),
        make_read_memory(deps),
        make_read_run_history(deps),
        make_read_documents_meta(deps),
        make_read_library_meta(deps),
    ]

    if deps.langchain_chat_model is None:
        logger.warning(
            "create_chat_agent: langchain_chat_model is None — "
            "returning tool list only (no LangGraph graph built)."
        )
        # Return a lightweight stub so callers can inspect tools without a real model.
        return _AgentStub(tools=tools, system_prompt=system_prompt)

    from langgraph.prebuilt import create_react_agent

    return create_react_agent(
        model=deps.langchain_chat_model,
        tools=tools,
        state_modifier=system_prompt,
    )


class _AgentStub:
    """Minimal stub returned when no langchain_chat_model is available.

    Exposes .tools and .system_prompt for test assertions.
    """

    def __init__(self, tools: list, system_prompt: str) -> None:
        self.tools = tools
        self.system_prompt = system_prompt
        self.tool_names = [t.name for t in tools]
