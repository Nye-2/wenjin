"""Task tool for subagent delegation."""

from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .registry import registry


class TaskInput(BaseModel):
    """Input for task tool."""
    description: str = Field(description="Brief description of the task")
    prompt: str = Field(description="Detailed instructions for the subagent")
    subagent_type: str = Field(description="Type of subagent to use (scout, writer, synthesizer, analyst)")
    max_turns: Optional[int] = Field(default=None, description="Maximum turns for the subagent")


@tool(args_schema=TaskInput)
async def task_tool(
    description: str,
    prompt: str,
    subagent_type: str,
    max_turns: Optional[int] = None,
) -> str:
    """Delegate a task to a specialized subagent.

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
    # Get subagent configuration
    config = registry.get(subagent_type)
    if not config:
        available = list(registry._subagents.keys())
        return f"Error: Unknown subagent type '{subagent_type}'. Available types: {available}"

    # Use configured max_turns if not specified
    if max_turns is None:
        max_turns = config.max_turns

    # Note: Actual subagent execution is handled by SubagentExecutor
    # This returns a task request that gets processed asynchronously
    return f"[Task delegated to {config.name}]\nDescription: {description}\nPrompt: {prompt[:200]}..."
