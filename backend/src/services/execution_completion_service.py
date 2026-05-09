"""Execution completion delivery service.

Spec §4.2.3: When an execution completes, append a system-role message to the
workspace's thread so the chat agent can pick it up and render a result_card.

Option C (V1 — no migration): store kind + payload as JSON in the message content.
"""

from __future__ import annotations

import json
import logging

from src.agents.contracts.task_report import TaskReport

logger = logging.getLogger(__name__)


class ExecutionCompletionService:
    """Delivers execution completion to the workspace chat thread.

    Writes a ``role="system"`` message whose content is JSON-encoded:

    .. code-block:: json

        {
            "kind": "execution_completed",
            "execution_id": "...",
            "task_report": { ... }
        }

    The chat agent and frontend interpret this on retrieval.
    """

    def __init__(
        self,
        *,
        thread_service,
        execution_service,
        workspace_service=None,
    ) -> None:
        self.threads = thread_service
        self.executions = execution_service
        self.workspaces = workspace_service

    async def deliver(self, execution_id: str, task_report: TaskReport) -> str | None:
        """Append a system message to the workspace's thread.

        Args:
            execution_id: ID of the completed execution.
            task_report: The completed TaskReport.

        Returns:
            A message identifier string, or None if delivery was skipped/failed.
        """
        execution = await self.executions.get_by_id(execution_id)
        if execution is None:
            logger.warning("deliver: execution %s not found", execution_id)
            return None

        thread_id = await self._resolve_thread_id(execution.workspace_id)
        if thread_id is None:
            logger.warning(
                "deliver: workspace %s has no thread",
                execution.workspace_id,
            )
            return None

        payload = {
            "kind": "execution_completed",
            "execution_id": execution_id,
            "task_report": task_report.model_dump(mode="json"),
        }

        try:
            msg_id = await self._append_system_message(thread_id, payload)
            return msg_id
        except Exception:
            logger.exception(
                "failed to append completion message",
                extra={"thread_id": thread_id, "execution_id": execution_id},
            )
            return None

    async def _resolve_thread_id(self, workspace_id: str) -> str | None:
        """Resolve the thread_id for a workspace (1:1 mapping from Task 1.1)."""
        if self.workspaces is None:
            return None
        ws = await self.workspaces.get_by_id(workspace_id)
        if ws is None:
            return None
        return getattr(ws, "thread_id", None)

    async def _append_system_message(self, thread_id: str, payload: dict) -> str:
        """Append the system message via ThreadService.

        ThreadService.add_message requires the Thread ORM object, so we fetch
        it first. Returns a synthetic message identifier.
        """
        thread = await self.threads.get_by_id(thread_id)
        if thread is None:
            raise ValueError(f"thread {thread_id} not found")

        msg = await self.threads.add_message(
            thread,
            role="system",
            content=json.dumps(payload, ensure_ascii=False),
        )
        # add_message returns the message dict; use timestamp as stable identifier
        return msg.get("timestamp", thread_id)
