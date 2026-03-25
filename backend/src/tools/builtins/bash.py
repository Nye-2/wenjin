"""Bash command execution tool."""

from __future__ import annotations

from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from src.agents.thread_state import ThreadState
from src.sandbox.runtime import resolve_runtime_sandbox


class BashInput(BaseModel):
    """Input for bash tool."""

    command: str = Field(description="The bash command to execute")
    timeout: int = Field(default=120, description="Timeout in seconds")


@tool("bash", args_schema=BashInput)
async def bash_tool(
    command: str,
    timeout: int = 120,
    state: Annotated[ThreadState, InjectedState] | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Execute a bash command inside the current thread sandbox."""
    try:
        sandbox = await resolve_runtime_sandbox(state, config)
        result = await sandbox.execute_command(command, timeout=timeout)
    except Exception as exc:
        return f"Error executing command: {exc}"

    output: list[str] = []
    if result.stdout:
        output.append(result.stdout)
    if result.stderr:
        output.append(result.stderr)

    rendered = "\n".join(part.rstrip("\n") for part in output if part).strip()
    if rendered:
        return rendered

    return f"Command completed with exit code {result.exit_code}"
