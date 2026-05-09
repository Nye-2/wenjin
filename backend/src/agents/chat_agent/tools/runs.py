"""read_run_history tool — reads past execution runs for this workspace."""

from __future__ import annotations

from langchain_core.tools import tool


def make_read_run_history(deps):
    """Return a read_run_history tool bound to the given deps.

    Args:
        deps: ChatAgentDeps instance.

    Returns:
        A langchain @tool-decorated async function.
    """

    @tool
    async def read_run_history(limit: int = 10) -> dict:
        """Read recent execution run history for this workspace.

        Returns a list of past runs with status, title, and summary.

        Args:
            limit: Maximum number of runs to return (default 10).
        """
        runs = await deps.run_history_service.list(deps.workspace_id, limit=limit)
        return {
            "runs": [
                {
                    "id": r.id,
                    "execution_id": r.execution_id,
                    "capability_id": r.capability_id,
                    "title": r.title,
                    "summary": r.summary,
                    "status": r.status,
                    "duration_seconds": r.duration_seconds,
                }
                for r in runs
            ]
        }

    return read_run_history
