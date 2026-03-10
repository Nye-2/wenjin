"""LangChain tool wrappers for sandbox operations."""

from typing import Optional

from langchain_core.tools import tool

from src.sandbox.base import Sandbox


def _get_sandbox_from_config(config: dict) -> Sandbox:
    """Extract sandbox from tool config."""
    configurable = config.get("configurable", {})
    sandbox = configurable.get("sandbox")
    if sandbox is None:
        raise ValueError("Sandbox not found in tool config")
    return sandbox


@tool
async def bash(description: str, command: str) -> str:
    """Execute a bash command in the sandbox.

    Use this for shell operations like file manipulation,
    running scripts, or system commands.

    Args:
        description: Brief description of what this command does.
        command: The bash command to execute.

    Returns:
        Command output or error message.
    """
    pass  # Implementation via config injection


@tool
async def ls(description: str, path: str) -> str:
    """List directory contents in tree format.

    Args:
        description: Brief description of why you're listing this directory.
        path: Absolute path to the directory.

    Returns:
        Directory contents in tree format.
    """
    pass


@tool
async def read_file(
    description: str,
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """Read the contents of a text file.

    Args:
        description: Brief description of why you're reading this file.
        path: Absolute path to the file.
        start_line: Optional starting line number (1-indexed).
        end_line: Optional ending line number (1-indexed).

    Returns:
        File contents.
    """
    pass


@tool
async def write_file(
    description: str,
    path: str,
    content: str,
    append: bool = False,
) -> str:
    """Write content to a file.

    Args:
        description: Brief description of why you're writing this file.
        path: Absolute path to the file.
        content: Content to write.
        append: Whether to append to existing file.

    Returns:
        "OK" on success or error message.
    """
    pass


@tool
async def str_replace(
    description: str,
    path: str,
    old_str: str,
    new_str: str,
    replace_all: bool = False,
) -> str:
    """Replace a substring in a file.

    Args:
        description: Brief description of why you're replacing.
        path: Absolute path to the file.
        old_str: String to replace.
        new_str: Replacement string.
        replace_all: Replace all occurrences if True.

    Returns:
        "OK" on success or error message.
    """
    pass


# Tool instances for direct use
bash_tool = bash
ls_tool = ls
read_file_tool = read_file
write_file_tool = write_file
str_replace_tool = str_replace


def create_sandbox_tools() -> list:
    """Create all sandbox tool instances.

    Returns:
        List of LangChain tool instances.
    """
    return [
        bash,
        ls,
        read_file,
        write_file,
        str_replace,
    ]
