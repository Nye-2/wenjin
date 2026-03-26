"""SubagentExecutor - background task execution with thread pools."""

import asyncio
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from src.subagents.models import SubagentStatus
from src.subagents.registry import SubagentConfig


# Note: ExecutorSubagentResult is different from SubagentResult in models.py
# This class tracks internal execution state with timing and message history
@dataclass
class ExecutorSubagentResult:
    """Internal execution state tracking (different from final SubagentResult)."""
    task_id: str
    status: SubagentStatus = SubagentStatus.PENDING
    result: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ai_messages: list[dict[str, Any]] = field(default_factory=list)


# Alias for backward compatibility
SubagentResult = ExecutorSubagentResult


# Global thread pools
_scheduler_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-scheduler-")
_execution_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-exec-")

# Background task tracking
_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()


def get_background_task_result(task_id: str) -> SubagentResult | None:
    with _background_tasks_lock:
        return _background_tasks.get(task_id)


def list_background_tasks() -> list[SubagentResult]:
    with _background_tasks_lock:
        return list(_background_tasks.values())


def _filter_tools(
    all_tools: list[BaseTool],
    allowed: list[str] | None,
    disallowed: list[str] | None,
) -> list[BaseTool]:
    """Filter tools by allowlist/denylist."""
    result = list(all_tools)
    if allowed:
        allowed_set = set(allowed)
        result = [t for t in result if t.name in allowed_set]
    if disallowed:
        disallowed_set = set(disallowed)
        result = [t for t in result if t.name not in disallowed_set]
    return result


class SubagentExecutor:
    """Executes subagent tasks with optional background threading."""

    def __init__(
        self,
        config: SubagentConfig,
        tools: list[BaseTool],
        parent_model: str | None = None,
        thread_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
    ):
        self.config = config
        self.parent_model = parent_model
        self.thread_id = thread_id
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.trace_id = trace_id or str(uuid.uuid4())[:12]
        self.tools = _filter_tools(
            tools,
            list(config.allowed_tools) if config.allowed_tools else None,
            list(config.disallowed_tools) if config.disallowed_tools else None,
        )

    def _create_agent(self):
        """Create a lightweight agent for subagent execution."""
        from src.models.factory import create_chat_model

        model_name = self.parent_model
        if not model_name:
            try:
                from src.config import get_default_model_id
                model_name = get_default_model_id()
            except Exception:
                model_name = "default"

        model = create_chat_model(model_name, thinking_enabled=False)

        from src.subagents.graph import create_academic_agent_graph

        return create_academic_agent_graph(
            model,
            self.tools,
            system_prompt=self.config.system_prompt,
            max_turns=self.config.max_turns,
        )

    @staticmethod
    def _serialize_message_content(content: Any) -> str:
        """Flatten model message content into text."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and "text" in block:
                    text_parts.append(str(block["text"]))
            return "\n".join(part for part in text_parts if part)
        if content is None:
            return ""
        return str(content)

    @staticmethod
    def _capture_ai_message(
        result_holder: SubagentResult,
        message: AIMessage,
    ) -> None:
        """Append unique AI messages to execution history."""
        message_dict = message.model_dump()
        message_id = message_dict.get("id")

        if message_id and any(msg.get("id") == message_id for msg in result_holder.ai_messages):
            return
        if not message_id and message_dict in result_holder.ai_messages:
            return

        result_holder.ai_messages.append(message_dict)

    @classmethod
    def _extract_result_from_messages(cls, messages: list[Any]) -> str:
        """Extract the final AI response text from streamed messages."""
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                return cls._serialize_message_content(message.content)

        if messages:
            last_message = messages[-1]
            if hasattr(last_message, "content"):
                return cls._serialize_message_content(last_message.content)
            return str(last_message)

        return "No response generated"

    async def _aexecute(
        self,
        task: str,
        result_holder: SubagentResult | None = None,
    ) -> SubagentResult:
        """Async execution path that supports async-only tools."""
        if result_holder is None:
            result_holder = SubagentResult(task_id=str(uuid.uuid4())[:12])

        result_holder.status = SubagentStatus.RUNNING
        result_holder.started_at = datetime.now(UTC)

        try:
            agent = self._create_agent()
            run_config: dict[str, Any] = {"recursion_limit": self.config.max_turns}
            configurable: dict[str, Any] = {}
            if self.thread_id:
                configurable["thread_id"] = self.thread_id
            if self.workspace_id:
                configurable["workspace_id"] = self.workspace_id
            if self.user_id:
                configurable["user_id"] = self.user_id
            if self.parent_model:
                configurable["model_name"] = self.parent_model
            if configurable:
                run_config["configurable"] = configurable

            final_state: dict[str, Any] | None = None
            async for chunk in agent.astream(
                {"messages": [("human", task)]},
                config=run_config,
                stream_mode="values",
            ):
                final_state = chunk
                messages = chunk.get("messages", [])
                if messages and isinstance(messages[-1], AIMessage):
                    self._capture_ai_message(result_holder, messages[-1])

            messages = final_state.get("messages", []) if final_state else []
            result_holder.result = self._extract_result_from_messages(messages)
            result_holder.status = SubagentStatus.COMPLETED
        except Exception as e:
            result_holder.error = str(e)
            result_holder.status = SubagentStatus.FAILED
        finally:
            result_holder.completed_at = datetime.now(UTC)

        return result_holder

    async def aexecute(
        self,
        task: str,
        result_holder: SubagentResult | None = None,
    ) -> SubagentResult:
        """Public async execution API for subagents."""
        return await self._aexecute(task, result_holder=result_holder)

    def execute(
        self,
        task: str,
        result_holder: SubagentResult | None = None,
    ) -> SubagentResult:
        """Synchronous wrapper around async execution."""
        try:
            return asyncio.run(self._aexecute(task, result_holder=result_holder))
        except Exception as e:
            if result_holder is None:
                result_holder = SubagentResult(task_id=str(uuid.uuid4())[:12])
            result_holder.status = SubagentStatus.FAILED
            result_holder.error = str(e)
            result_holder.completed_at = datetime.now(UTC)
            return result_holder

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        """Background execution (returns task_id immediately)."""
        task_id = task_id or str(uuid.uuid4())[:12]
        result = SubagentResult(task_id=task_id)

        with _background_tasks_lock:
            _background_tasks[task_id] = result

        def _run():
            try:
                self.execute(task, result_holder=result)
            finally:
                with _background_tasks_lock:
                    _background_tasks.pop(task_id, None)

        _execution_pool.submit(_run)
        return task_id
