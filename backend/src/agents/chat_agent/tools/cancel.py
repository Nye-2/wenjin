"""cancel_run tool — cancels a running or pending execution."""

from __future__ import annotations

from langchain_core.tools import tool


def make_cancel_run(deps):
    """Return a cancel_run tool bound to the given deps.

    Args:
        deps: ChatAgentDeps instance.

    Returns:
        A langchain @tool-decorated async function.
    """

    @tool
    async def cancel_run(execution_id: str) -> dict:
        """Cancel a pending or running execution.

        Use when the user says "stop", "cancel", or similar.

        Args:
            execution_id: The execution ID to cancel.
        """
        record = await deps.execution_service.cancel_execution(execution_id)
        if record is None:
            return {"error": "not_found", "message": f"Execution {execution_id} not found."}
        return {"status": "cancelled", "execution_id": execution_id}

    return cancel_run
