"""read_memory tool — reads workspace memory facts."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool


def make_read_memory(deps):
    """Return a read_memory tool bound to the given deps.

    Args:
        deps: ChatAgentDeps instance.

    Returns:
        A langchain @tool-decorated async function.
    """

    @tool
    async def read_memory(category: Optional[str] = None, k: int = 15) -> dict:
        """Read workspace memory facts.

        Returns the top-k memory facts, optionally filtered by category.

        Args:
            category: Optional category filter (e.g. "user_preferences").
            k: Maximum number of facts to return (default 15).
        """
        facts = await deps.memory_service.top(
            deps.workspace_id,
            k=k,
            category=category,
        )
        return {
            "facts": [
                {
                    "id": f.id,
                    "category": f.category,
                    "content": f.content,
                    "confidence": f.confidence,
                }
                for f in facts
            ]
        }

    return read_memory
