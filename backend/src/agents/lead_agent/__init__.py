"""Lead agent — right-side execution engine.

The lead agent runs LangGraph subagents for a capability invocation.  Entry
point: :class:`src.agents.lead_agent.v2.runtime.LeadAgentRuntime`.

The *left-side* conversational agent (the one the user types at) lives in
:mod:`src.agents.chat_agent`.
"""

from .v2.runtime import LeadAgentRuntime

__all__ = ["LeadAgentRuntime"]
