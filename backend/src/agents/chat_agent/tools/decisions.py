"""write_decision and read_decisions tools — manage workspace decisions."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool


def make_write_decision(deps):
    """Return a write_decision tool bound to the given deps.

    Args:
        deps: ChatAgentDeps instance.

    Returns:
        A langchain @tool-decorated async function.
    """

    @tool
    async def write_decision(key: str, value: str, confidence: float = 1.0) -> dict:
        """Record a user decision or preference for this workspace.

        Use when the user states a clear preference (e.g. "I always use APA",
        "my research language is English").

        Args:
            key: Short identifier for this decision (e.g. "citation_style").
            value: The decision value (e.g. "APA").
            confidence: Confidence level 0.0–1.0, default 1.0.
        """
        decision = await deps.decisions_service.set(
            deps.workspace_id,
            key=key,
            value=value,
            extracted_by="chat_agent",
            confidence=confidence,
        )
        return {"status": "ok", "decision_id": decision.id}

    return write_decision


def make_read_decisions(deps):
    """Return a read_decisions tool bound to the given deps.

    Args:
        deps: ChatAgentDeps instance.

    Returns:
        A langchain @tool-decorated async function.
    """

    @tool
    async def read_decisions() -> dict:
        """Read all active workspace decisions.

        Returns a dict of all current key→value decisions for this workspace.
        """
        decisions = await deps.decisions_service.get_active(deps.workspace_id)
        return {"decisions": decisions}

    return read_decisions
