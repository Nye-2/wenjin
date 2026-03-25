"""File operation tools backed by the per-thread sandbox."""

from __future__ import annotations

from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from src.agents.thread_state import ThreadState
from src.sandbox.runtime import resolve_runtime_sandbox

VIRTUAL_USER_DATA_PREFIX = "/mnt/user-data"
VIRTUAL_WORKSPACE_PREFIX = f"{VIRTUAL_USER_DATA_PREFIX}/workspace"


class ReadFileInput(BaseModel):
    """Input for read_file tool."""

    file_path: str = Field(description="Path to the file to read")
    start_line: int | None = Field(default=None, description="Start line number (1-indexed)")
    end_line: int | None = Field(default=None, description="End line number (1-indexed)")


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


def _to_virtual_path(raw_path: str, *, default_dir: str = VIRTUAL_WORKSPACE_PREFIX) -> str:
    """Resolve tool-relative paths into the sandbox virtual filesystem."""
    path = str(raw_path or "").strip()
    if not path or path == ".":
        return default_dir

    if path.startswith(VIRTUAL_USER_DATA_PREFIX):
        return path

    if path.startswith("/"):
        raise ValueError(
            f"Absolute paths must stay under {VIRTUAL_USER_DATA_PREFIX}: {path}"
        )

    normalized = path[2:] if path.startswith("./") else path
    normalized = normalized.strip("/")
    if not normalized:
        return default_dir

    top_level, _, remainder = normalized.partition("/")
    if top_level in {"workspace", "uploads", "outputs"}:
        suffix = f"/{remainder}" if remainder else ""
        return f"{VIRTUAL_USER_DATA_PREFIX}/{top_level}{suffix}"

    return f"{default_dir}/{normalized}"


async def _get_sandbox(
    state: ThreadState | None,
    config: RunnableConfig | None,
):
    return await resolve_runtime_sandbox(state, config)


def _render_line_numbered_content(
    content: str,
    *,
    start_line: int | None,
    end_line: int | None,
) -> str:
    """Render file content with stable 1-based line numbers."""
    lines = content.splitlines()

    if start_line is not None or end_line is not None:
        start_idx = max((start_line or 1) - 1, 0)
        end_idx = max(end_line or len(lines), 0)
        selected = lines[start_idx:end_idx]
        start_num = start_idx + 1
    else:
        selected = lines
        start_num = 1

    if not selected:
        return ""

    return "\n".join(
        f"{start_num + index:6d}| {line}"
        for index, line in enumerate(selected)
    )


@tool("read_file", args_schema=ReadFileInput)
async def read_file_tool(
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    state: Annotated[ThreadState, InjectedState] | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Read a file from the current thread sandbox."""
    try:
        sandbox = await _get_sandbox(state, config)
        virtual_path = _to_virtual_path(file_path)
        content = await sandbox.read_file(virtual_path)
        rendered = _render_line_numbered_content(
            content,
            start_line=start_line,
            end_line=end_line,
        )
        return rendered or "(empty file)"
    except Exception as exc:
        return f"Error reading file: {exc}"


@tool("write_file", args_schema=WriteFileInput)
async def write_file_tool(
    file_path: str,
    content: str,
    mode: str = "write",
    state: Annotated[ThreadState, InjectedState] | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Write content to a file in the current thread sandbox."""
    try:
        sandbox = await _get_sandbox(state, config)
        virtual_path = _to_virtual_path(file_path)
        append = mode == "append"
        await sandbox.write_file(virtual_path, content, append=append)
        action = "appended to" if append else "wrote to"
        return f"Successfully {action} {virtual_path}"
    except Exception as exc:
        return f"Error writing file: {exc}"


@tool("str_replace", args_schema=StrReplaceInput)
async def str_replace_tool(
    file_path: str,
    old_str: str,
    new_str: str,
    replace_all: bool = False,
    state: Annotated[ThreadState, InjectedState] | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Replace a string in a sandboxed file."""
    try:
        sandbox = await _get_sandbox(state, config)
        virtual_path = _to_virtual_path(file_path)
        content = await sandbox.read_file(virtual_path)
        if old_str not in content:
            preview = old_str[:50]
            suffix = "..." if len(old_str) > 50 else ""
            return f"String not found in file: {preview}{suffix}"

        if replace_all:
            replacement_count = content.count(old_str)
            updated = content.replace(old_str, new_str)
        else:
            replacement_count = 1
            updated = content.replace(old_str, new_str, 1)

        await sandbox.write_file(virtual_path, updated, append=False)
        return f"Replaced {replacement_count} occurrence(s) in {virtual_path}"
    except Exception as exc:
        return f"Error replacing string: {exc}"


@tool("ls", args_schema=LsInput)
async def ls_tool(
    path: str = ".",
    state: Annotated[ThreadState, InjectedState] | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """List directory contents inside the current thread sandbox."""
    try:
        sandbox = await _get_sandbox(state, config)
        virtual_path = _to_virtual_path(path)
        entries = await sandbox.list_dir(virtual_path, max_depth=0)
        result = [f"Contents of {virtual_path}:"]
        for entry in entries:
            if entry.is_dir:
                result.append(f"[DIR] {entry.name}/")
                continue

            size = entry.size or 0
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size // 1024}KB"
            else:
                size_str = f"{size // (1024 * 1024)}MB"
            result.append(f"[FILE] {entry.name} ({size_str})")

        return "\n".join(result)
    except Exception as exc:
        return f"Error listing directory: {exc}"
