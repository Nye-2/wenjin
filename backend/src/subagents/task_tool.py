"""Task delegation tool backed by the global subagent manager."""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field
from typing import Annotated

from src.agents.thread_state import ThreadState
from src.subagents.context_snapshot import build_subagent_context_snapshot
from src.subagents.academic.registry import get_all_subagent_types, get_subagent_config
from src.subagents.manager import SubagentAccessError
from src.subagents.models import SubagentStatus
from src.subagents.runtime import get_manager
from src.subagents.task_builder import (
    SubagentRuntimeContext,
    build_subagent_metadata,
    build_subagent_task,
)


class TaskInput(BaseModel):
    """Input for task tool."""

    description: str = Field(description="Brief description of the task")
    prompt: str = Field(description="Detailed instructions for the subagent")
    subagent_type: str = Field(description="Type of subagent to use (scout, writer, synthesizer, analyst)")
    max_turns: int | None = Field(default=None, description="Maximum turns for the subagent")


def _format_subagent_result(name: str, status: SubagentStatus, body: str | None) -> str:
    """Format tool-facing output from a manager-backed subagent run."""
    content = body or "Unknown error"
    if status == SubagentStatus.COMPLETED:
        return f"[{name} completed]\n{content}"
    if status == SubagentStatus.TIMED_OUT:
        return f"[{name} timed out]\n{content}"
    if status == SubagentStatus.CANCELLED:
        return f"[{name} failed]\nCancelled"
    return f"[{name} failed]\n{content}"


@tool("task", args_schema=TaskInput)
async def task_tool(
    description: str,
    prompt: str,
    subagent_type: str,
    max_turns: int | None = None,
    config: RunnableConfig | None = None,
    state: Annotated[ThreadState, InjectedState] | None = None,
) -> str:
    """Delegate a task to a specialized subagent for parallel execution.

    Use this tool to delegate complex tasks to specialized agents:
    - scout: For literature search and paper discovery
    - writer: For academic writing tasks
    - synthesizer: For knowledge synthesis and analysis
    - analyst: For data analysis and experiments

    The subagent will work independently and return results.

    Args:
        description: Brief task description
        prompt: Detailed instructions
        subagent_type: Type of subagent to use
        max_turns: Optional max turns override

    Returns:
        Results from the subagent
    """
    try:
        subagent_config = get_subagent_config(subagent_type)
    except ValueError:
        available = get_all_subagent_types()
        return f"Error: Unknown subagent type '{subagent_type}'. Available: {available}"

    runtime_config = config or {}
    runtime_context = SubagentRuntimeContext.from_mapping(
        runtime_config.get("configurable", {})
    )
    context_snapshot = await build_subagent_context_snapshot(
        runtime_context=runtime_context,
        state=state,
    )
    manager = get_manager()

    task = build_subagent_task(
        manager._config,
        prompt=prompt,
        thread_id=runtime_context.resolve_thread_id(fallback_prefix="subagent-tool"),
        fallback_max_turns=subagent_config.max_turns,
        requested_max_turns=max_turns,
        tools=subagent_config.tools,
        metadata=build_subagent_metadata(
            description=description,
            subagent_type=subagent_type,
            system_prompt=subagent_config.system_prompt,
            context_snapshot=context_snapshot,
            runtime_context=runtime_context,
            include_workspace=runtime_context.thread_id is not None,
            include_user=runtime_context.thread_id is not None,
        ),
    )
    try:
        await manager.spawn(task)
    except SubagentAccessError:
        return _format_subagent_result(
            subagent_config.name,
            SubagentStatus.FAILED,
            "Thread not found",
        )

    result = await manager.wait_for_completion(
        task.thread_id,
        task.task_id,
        user_id=task.metadata.get("user_id"),
    )
    if result is None:
        return _format_subagent_result(
            subagent_config.name,
            SubagentStatus.FAILED,
            "Subagent task could not be loaded",
        )

    if result.status == SubagentStatus.COMPLETED:
        return _format_subagent_result(subagent_config.name, result.status, result.output)
    return _format_subagent_result(subagent_config.name, result.status, result.error)
