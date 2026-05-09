"""query_run_progress tool — queries the execution graph / progress for a run."""

from __future__ import annotations

from langchain_core.tools import tool


def make_query_run_progress(deps):
    """Return a query_run_progress tool bound to the given deps.

    Args:
        deps: ChatAgentDeps instance.

    Returns:
        A langchain @tool-decorated async function.
    """

    @tool
    async def query_run_progress(execution_id: str) -> dict:
        """Query the current progress of an execution run.

        Returns the execution graph node states and the overall status.

        Args:
            execution_id: The execution ID returned by dispatch_capability.
        """
        record = await deps.execution_service.get_by_id(execution_id)
        if record is None:
            return {"error": "not_found", "message": f"Execution {execution_id} not found."}

        graph = await deps.execution_service.get_execution_graph(execution_id)
        return {
            "execution_id": execution_id,
            "status": record.status,
            "progress": getattr(record, "progress", None),
            "node_states": graph,
        }

    return query_run_progress
