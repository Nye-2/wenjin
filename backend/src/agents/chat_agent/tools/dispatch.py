"""dispatch_capability tool — dispatches a capability to the lead agent execution layer."""

from __future__ import annotations

from langchain_core.tools import tool

from src.agents.contracts.task_brief import TaskBrief


def make_dispatch_capability(deps):
    """Return a dispatch_capability tool bound to the given deps.

    Args:
        deps: ChatAgentDeps instance.

    Returns:
        A langchain @tool-decorated async function.
    """

    @tool
    async def dispatch_capability(
        capability_id: str,
        brief: dict,
        raw_message: str,
    ) -> dict:
        """Dispatch a capability to the lead execution layer. Returns execution_id or error.

        Use this tool when the user clearly requests a capability to be executed
        (e.g. deep research, outline generation, paper writing).

        Args:
            capability_id: Which capability to invoke (e.g. "deep_research").
            brief: Capability-specific parameters per its brief_schema.
            raw_message: Original user message that triggered this dispatch.
        """
        # 1. Lead-busy check — filter by pending/running in Python since
        #    list_executions uses `status` (list), not `statuses`.
        all_active = await deps.execution_service.list_executions(
            workspace_id=deps.workspace_id,
            status=["pending", "running"],
        )
        if all_active:
            active = all_active[0]
            feature_label = getattr(active, "feature_id", "unknown")
            progress = getattr(active, "progress", 0)
            return {
                "error": "lead_busy",
                "message": (
                    f"我正在跑「{feature_label}」（{progress}%）。"
                    "要不要先看看进度？"
                ),
            }

        # 2. Validate capability exists
        try:
            await deps.capability_resolver.resolve(capability_id, deps.workspace_type)
        except Exception as exc:
            return {"error": "unknown_capability", "message": str(exc)}

        # 3. Fetch decisions for context
        decisions = await deps.decisions_service.get_active(deps.workspace_id)

        # 4. Construct + persist + dispatch
        task_brief = TaskBrief(
            capability_id=capability_id,
            brief=brief,
            raw_message=raw_message,
            decisions=decisions,
            workspace_id=deps.workspace_id,
        )
        execution = await deps.execution_service.create_execution(
            workspace_id=deps.workspace_id,
            user_id=deps.user_id,
            execution_type="capability",
            feature_id=capability_id,
            params={"brief": task_brief.model_dump(mode="json")},
        )
        return {
            "execution_id": execution.id,
            "capability_id": capability_id,
            "status": "dispatched",
        }

    return dispatch_capability
