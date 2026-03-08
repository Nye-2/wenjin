"""Bash command execution tool."""

import asyncio

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class BashInput(BaseModel):
    """Input for bash tool."""
    command: str = Field(description="The bash command to execute")
    timeout: int = Field(default=120, description="Timeout in seconds")


@tool(args_schema=BashInput)
async def bash_tool(command: str, timeout: int = 120) -> str:
    """Execute a bash command and return the output.

    Use this tool to run shell commands. Be careful with commands that
    modify files or system state.

    Args:
        command: The bash command to execute
        timeout: Maximum execution time in seconds

    Returns:
        Command output (stdout and stderr combined)
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except TimeoutError:
            process.kill()
            return f"Command timed out after {timeout} seconds"

        output = []
        if stdout:
            output.append(stdout.decode("utf-8", errors="replace"))
        if stderr:
            output.append(stderr.decode("utf-8", errors="replace"))

        result = "\n".join(output).strip()
        if not result:
            result = f"Command completed with exit code {process.returncode}"

        return result

    except Exception as e:
        return f"Error executing command: {str(e)}"
