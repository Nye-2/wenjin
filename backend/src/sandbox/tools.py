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
async def bash(command: str, description: str = "") -> str:
    """Execute a bash command in the sandbox.

    Use this for shell operations like file manipulation,
    running scripts, or system commands.

    Args:
        command: The bash command to execute.
        description: Brief description of what this command does.

    Returns:
        Command output or error message.
    """
    # Actual execution handled by middleware via sandbox injection
    return ""


@tool
async def list_dir(
    path: str,
    max_depth: int = 2,
    description: str = "",
) -> str:
    """List directory contents in tree format.

    Args:
        path: Absolute path to the directory.
        max_depth: Maximum depth to traverse.
        description: Brief description of why you're listing this directory.

    Returns:
        Directory contents in tree format.
    """
    return ""


@tool
async def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    description: str = "",
) -> str:
    """Read the contents of a text file.

    Args:
        path: Absolute path to the file.
        start_line: Optional starting line number (1-indexed).
        end_line: Optional ending line number (1-indexed).
        description: Brief description of why you're reading this file.

    Returns:
        File contents.
    """
    return ""


@tool
async def write_file(
    path: str,
    content: str,
    append: bool = False,
    description: str = "",
) -> str:
    """Write content to a file.

    Args:
        path: Absolute path to the file.
        content: Content to write.
        append: Whether to append to existing file.
        description: Brief description of why you're writing this file.

    Returns:
        "OK" on success or error message.
    """
    return "OK"


@tool
async def str_replace(
    path: str,
    old_str: str,
    new_str: str,
    replace_all: bool = False,
    description: str = "",
) -> str:
    """Replace a substring in a file.

    Args:
        path: Absolute path to the file.
        old_str: String to replace.
        new_str: Replacement string.
        replace_all: Replace all occurrences if True.
        description: Brief description of why you're replacing.

    Returns:
        "OK" on success or error message.
    """
    return "OK"


# Tool instances for direct access
bash_tool = bash
read_file_tool = read_file
write_file_tool = write_file
str_replace_tool = str_replace
list_dir_tool = list_dir


def create_sandbox_tools() -> list:
    """Create all sandbox tool instances.

    Returns:
        List of LangChain tool instances.
    """
    return [
        bash,
        read_file,
        write_file,
        str_replace,
        list_dir,
    ]
