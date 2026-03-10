"""Subagent task executor."""

import asyncio
from datetime import datetime
from typing import Any, Optional

from .async_events import AsyncEventStream
from .async_graph import GraphTemplateRegistry, create_default_subagent_graph
from .async_models import SubagentTaskDef, SubagentTaskStatus, SubagentTaskEvent, TaskResult
from .async_limiter import DualLayerLimiter


class AsyncSubagentExecutor:
    """Executes individual subagent tasks."""

    def __init__(
        self,
        llm: Any,
        tools: list,
        event_stream: AsyncEventStream,
        graph_registry: GraphTemplateRegistry,
    ):
        self._llm = llm
        self._tools = tools
        self._event_stream = event_stream
        self._graph_registry = graph_registry

    async def execute(self, task: SubagentTaskDef) -> TaskResult:
        """Execute a subagent task.

        Args:
            task: The task definition.

        Returns:
            TaskResult with execution outcome.
        """
        start_time = datetime.now()

        try:
            await self._publish_event(task, "task_started", {"prompt": task.prompt})

            graph = self._get_graph(task.graph_template)

            from langchain_core.messages import HumanMessage
            result = await asyncio.wait_for(
                graph.ainvoke({"messages": [HumanMessage(content=task.prompt)]}),
                timeout=task.timeout,
            )

            messages = result.get("messages", [])
            output = messages[-1].content if messages else ""

            await self._publish_event(task, "task_completed", {"output": output})

            return TaskResult(
                task_id=task.task_id,
                status=SubagentTaskStatus.COMPLETED,
                output=output,
                turns_used=len(messages) // 2,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

        except asyncio.TimeoutError:
            await self._publish_event(task, "task_failed", {"error": "Timeout"})
            return TaskResult(
                task_id=task.task_id,
                status=SubagentTaskStatus.TIMEOUT,
                error=f"Timed out after {task.timeout}s",
                duration_seconds=task.timeout,
            )

        except asyncio.CancelledError:
            await self._publish_event(task, "task_cancelled", {})
            return TaskResult(
                task_id=task.task_id,
                status=SubagentTaskStatus.CANCELLED,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )
        except Exception as e:
            await self._publish_event(task, "task_failed", {"error": str(e)})
            return TaskResult(
                task_id=task.task_id,
                status=SubagentTaskStatus.FAILED,
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
            )

    def _get_graph(self, template_name: str) -> Any:
        graph = self._graph_registry.get(template_name)
        if graph is None:
            graph = create_default_subagent_graph(self._llm, self._tools)
            self._graph_registry.register(template_name, graph)
        return graph

    async def _publish_event(self, task: SubagentTaskDef, event_type: str, data: dict):
        """Publish an event to the stream."""
        await self._event_stream.publish(SubagentTaskEvent(
            event_type=event_type,
            task_id=task.task_id,
            thread_id=task.thread_id,
            data=data,
        ))
