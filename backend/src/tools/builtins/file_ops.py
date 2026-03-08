"""File operation tools."""

from pathlib import Path
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ReadFileInput(BaseModel):
    """Input for read_file tool."""
    file_path: str = Field(description="Path to the file to read")
    start_line: Optional[int] = Field(default=None, description="Start line number (1-indexed)")
    end_line: Optional[int] = Field(default=None, description="End line number (1-indexed)")


class WriteFileInput(BaseModel):
    """Input for write_file tool."""
    file_path: str = Field(description="Path to the file to write")
    content: str = Field(description="Content to write to the file")
    mode: str = Field(default="write", description="Mode: 'write' or 'append'")


class StrReplaceInput(BaseModel):
    """Input for str_replace tool."""
    file_path: str = Field(description="Path to the file")
    old_str: str = Field(description="String to replace")
    new_str: str = Field(description="New string")
    replace_all: bool = Field(default=False, description="Replace all occurrences")


class LsInput(BaseModel):
    """Input for ls tool."""
    path: str = Field(default=".", description="Directory path to list")


@tool(args_schema=ReadFileInput)
async def read_file_tool(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """Read the contents of a file.

    Args:
        file_path: Path to the file to read
        start_line: Optional start line (1-indexed)
        end_line: Optional end line (1-indexed)

    Returns:
        File contents as string
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if start_line is not None or end_line is not None:
            start = (start_line or 1) - 1
            end = end_line or len(lines)
            lines = lines[start:end]

        # Add line numbers
        result = []
        start_num = (start_line or 1)
        for i, line in enumerate(lines):
            result.append(f"{start_num + i:6d}→{line.rstrip()}")

        return "\n".join(result)

    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool(args_schema=WriteFileInput)
async def write_file_tool(
    file_path: str,
    content: str,
    mode: str = "write",
) -> str:
    """Write content to a file.

    Args:
        file_path: Path to the file to write
        content: Content to write
        mode: 'write' to overwrite, 'append' to add to end

    Returns:
        Success message or error
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        write_mode = "a" if mode == "append" else "w"
        with open(path, write_mode, encoding="utf-8") as f:
            f.write(content)

        action = "appended to" if mode == "append" else "wrote to"
        return f"Successfully {action} {file_path}"

    except Exception as e:
        return f"Error writing file: {str(e)}"


@tool(args_schema=StrReplaceInput)
async def str_replace_tool(
    file_path: str,
    old_str: str,
    new_str: str,
    replace_all: bool = False,
) -> str:
    """Replace a string in a file.

    Args:
        file_path: Path to the file
        old_str: String to find and replace
        new_str: Replacement string
        replace_all: Replace all occurrences if True

    Returns:
        Success message with number of replacements
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if old_str not in content:
            return f"String not found in file: {old_str[:50]}..."

        if replace_all:
            count = content.count(old_str)
            content = content.replace(old_str, new_str)
        else:
            count = 1
            content = content.replace(old_str, new_str, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Replaced {count} occurrence(s) in {file_path}"

    except Exception as e:
        return f"Error replacing string: {str(e)}"


@tool(args_schema=LsInput)
async def ls_tool(path: str = ".") -> str:
    """List directory contents.

    Args:
        path: Directory path to list

    Returns:
        Directory listing as formatted string
    """
    try:
        dir_path = Path(path)
        if not dir_path.exists():
            return f"Error: Directory not found: {path}"

        if not dir_path.is_dir():
            return f"Error: Not a directory: {path}"

        result = [f"Contents of {path}:\n"]

        items = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))

        for item in items:
            if item.is_dir():
                result.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size // 1024}KB"
                else:
                    size_str = f"{size // (1024 * 1024)}MB"
                result.append(f"📄 {item.name} ({size_str})")

        return "\n".join(result)

    except Exception as e:
        return f"Error listing directory: {str(e)}"
