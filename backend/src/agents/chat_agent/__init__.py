"""Chat agent — the conversational entry point for a workspace thread.

The chat agent is what users talk to in the left panel.  It identifies intent,
asks clarifying questions, persists decisions, and dispatches workspace
capabilities to the right-side LeadAgentRuntime via the ``launch_feature`` tool.

It is *not* the right-side execution engine — that's
:mod:`src.agents.lead_agent.v2.runtime`.
"""

from .agent import apply_prompt_template, get_available_tools, make_chat_agent

__all__ = ["make_chat_agent", "apply_prompt_template", "get_available_tools"]
