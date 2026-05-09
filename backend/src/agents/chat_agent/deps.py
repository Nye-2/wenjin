"""ChatAgentDeps — dependency bundle for chat agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ChatAgentDeps:
    """All dependencies needed by the chat agent and its tools.

    Pass an instance of this to create_chat_agent() and each make_<tool>() factory.
    """

    workspace_id: str
    workspace_type: str
    user_id: str
    execution_service: Any
    capability_resolver: Any
    decisions_service: Any
    memory_service: Any
    run_history_service: Any
    documents_service: Any
    library_service: Any
    model_gateway: Any
    # Optional: pass a langchain BaseChatModel directly for the agent.
    # If None, create_chat_agent will not build the LangGraph graph (test mode).
    langchain_chat_model: Any = None
