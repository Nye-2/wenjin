"""Task delegation tool using SubagentExecutor."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.subagents.executor import SubagentExecutor, SubagentStatus
from src.subagents.registry import registry


class TaskInput(BaseModel):
    """Input for task tool."""
    description: str = Field(description="Brief description of the task")
    prompt: str = Field(description="Detailed instructions for the subagent")
    subagent_type: str = Field(description="Type of subagent to use (scout, writer, synthesizer, analyst)")
    max_turns: int | None = Field(default=None, description="Maximum turns for the subagent")


@tool(args_schema=TaskInput)
async def task_tool(
    description: str,
    prompt: str,
    subagent_type: str,
    max_turns: int | None = None,
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
    config = registry.get(subagent_type)
    if not config:
        available = list(registry._subagents.keys())
        return f"Error: Unknown subagent type '{subagent_type}'. Available: {available}"

    if max_turns is not None:
        config = type(config)(
            name=config.name,
            description=config.description,
            system_prompt=config.system_prompt,
            allowed_tools=config.allowed_tools,
            max_turns=max_turns,
        )

    from src.agents.lead_agent.agent import get_available_tools
    tools = get_available_tools(subagent_enabled=False)

    executor = SubagentExecutor(config=config, tools=tools)
    result = executor.execute(prompt)

    if result.status == SubagentStatus.COMPLETED:
        return f"[{config.name} completed]\n{result.result}"
    elif result.status == SubagentStatus.TIMED_OUT:
        return f"[{config.name} timed out]\n{result.error or 'Exceeded time limit'}"
    else:
        return f"[{config.name} failed]\n{result.error or 'Unknown error'}"
