"""File operation tools backed by the per-thread sandbox."""

from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from src.agents.thread_state import ThreadState
from src.sandbox import Sandbox
from src.sandbox.file_operation_lock import get_file_operation_lock
from src.sandbox.runtime import resolve_runtime_sandbox

VIRTUAL_USER_DATA_PREFIX = "/mnt/user-data"
VIRTUAL_WORKSPACE_PREFIX = f"{VIRTUAL_USER_DATA_PREFIX}/workspace"
MAX_TOOL_OUTPUT_CHARS = 12000
DEFAULT_GLOB_MAX_RESULTS = 200
MAX_GLOB_MAX_RESULTS = 1000
DEFAULT_GREP_MAX_RESULTS = 100
MAX_GREP_MAX_RESULTS = 500
DEFAULT_GREP_MAX_FILE_SIZE_CHARS = 1_000_000
DEFAULT_LINE_SUMMARY_LENGTH = 200

IGNORE_PATTERNS = [
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    ".tox",
    ".nox",
    ".eggs",
    "*.egg-info",
    "site-packages",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".output",
    ".turbo",
    "target",
    "out",
    ".idea",
    ".vscode",
    ".DS_Store",
    "Thumbs.db",
    "*.log",
    "*.tmp",
    "*.temp",
    "*.bak",
    "*.cache",
    ".cache",
    "logs",
    ".coverage",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
]


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


class GlobInput(BaseModel):
    """Input for glob tool."""

    pattern: str = Field(description="Glob pattern, e.g. '**/*.py' or 'src/**/*.ts'")
    path: str = Field(default=".", description="Base directory path")
    include_dirs: bool = Field(default=False, description="Include directory matches")
    max_results: int = Field(default=DEFAULT_GLOB_MAX_RESULTS, description="Maximum results to return")


class GrepInput(BaseModel):
    """Input for grep tool."""

    pattern: str = Field(description="Search pattern (regex by default)")
    path: str = Field(default=".", description="Base directory path")
    glob_pattern: str | None = Field(default=None, description="Optional glob filter, e.g. '**/*.py'")
    literal: bool = Field(default=False, description="Treat pattern as literal string")
    case_sensitive: bool = Field(default=False, description="Case-sensitive matching")
    max_results: int = Field(default=DEFAULT_GREP_MAX_RESULTS, description="Maximum matches to return")


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


def _truncate_tool_output(text: str) -> str:
    if len(text) <= MAX_TOOL_OUTPUT_CHARS:
        return text
    return text[:MAX_TOOL_OUTPUT_CHARS] + "\n\n...[truncated]"


def _to_relative_path(base_path: str, full_path: str) -> str:
    if full_path == base_path:
        return "."
    prefix = f"{base_path.rstrip('/')}/"
    if full_path.startswith(prefix):
        return full_path[len(prefix):]
    return full_path


def _should_ignore_name(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in IGNORE_PATTERNS)


def _should_ignore_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and part != "."]
    return any(_should_ignore_name(part) for part in parts)


def _path_matches(pattern: str, relative_path: str) -> bool:
    pure = PurePosixPath(relative_path)
    if pure.match(pattern):
        return True
    if pattern.startswith("**/"):
        return pure.match(pattern[3:])
    return False


def _truncate_line(line: str, max_chars: int = DEFAULT_LINE_SUMMARY_LENGTH) -> str:
    line = line.rstrip("\n\r")
    if len(line) <= max_chars:
        return line
    return line[: max_chars - 3] + "..."


async def _get_sandbox(
    state: ThreadState | None,
    config: RunnableConfig | None,
) -> Sandbox:
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
        return _truncate_tool_output(rendered or "(empty file)")
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
        async with get_file_operation_lock(sandbox, virtual_path):
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
        async with get_file_operation_lock(sandbox, virtual_path):
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

        return _truncate_tool_output("\n".join(result))
    except Exception as exc:
        return f"Error listing directory: {exc}"


@tool("glob", args_schema=GlobInput)
async def glob_tool(
    pattern: str,
    path: str = ".",
    include_dirs: bool = False,
    max_results: int = DEFAULT_GLOB_MAX_RESULTS,
    state: Annotated[ThreadState, InjectedState] | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Find files using a glob pattern inside the current thread sandbox."""
    try:
        sandbox = await _get_sandbox(state, config)
        virtual_path = _to_virtual_path(path)
        bounded_max = max(1, min(max_results, MAX_GLOB_MAX_RESULTS))
        entries = await sandbox.list_dir(virtual_path, max_depth=8)

        matches: list[str] = []
        for entry in entries:
            if entry.is_dir and not include_dirs:
                continue
            relative_path = _to_relative_path(virtual_path, entry.path).replace("\\", "/")
            if relative_path == ".":
                continue
            if _should_ignore_path(relative_path):
                continue
            if _path_matches(pattern, relative_path):
                matches.append(entry.path)
                if len(matches) >= bounded_max:
                    break

        lines = [
            f"Glob pattern: {pattern}",
            f"Base path: {virtual_path}",
        ]
        if matches:
            lines.append(f"Matches ({len(matches)}):")
            lines.extend(f"- {match}" for match in matches)
        else:
            lines.append("No matches found.")

        if len(matches) >= bounded_max:
            lines.append(f"... results truncated to {bounded_max} entries")
        return _truncate_tool_output("\n".join(lines))
    except Exception as exc:
        return f"Error searching files: {exc}"


@tool("grep", args_schema=GrepInput)
async def grep_tool(
    pattern: str,
    path: str = ".",
    glob_pattern: str | None = None,
    literal: bool = False,
    case_sensitive: bool = False,
    max_results: int = DEFAULT_GREP_MAX_RESULTS,
    state: Annotated[ThreadState, InjectedState] | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Search file contents with regex/literal pattern inside thread sandbox."""
    try:
        sandbox = await _get_sandbox(state, config)
        virtual_path = _to_virtual_path(path)
        bounded_max = max(1, min(max_results, MAX_GREP_MAX_RESULTS))
        entries = await sandbox.list_dir(virtual_path, max_depth=8)

        regex_source = re.escape(pattern) if literal else pattern
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(regex_source, flags)

        matches: list[str] = []
        for entry in entries:
            if entry.is_dir:
                continue

            relative_path = _to_relative_path(virtual_path, entry.path).replace("\\", "/")
            if relative_path == "." or _should_ignore_path(relative_path):
                continue
            if glob_pattern and not _path_matches(glob_pattern, relative_path):
                continue

            content = await sandbox.read_file(entry.path)
            if len(content) > DEFAULT_GREP_MAX_FILE_SIZE_CHARS:
                continue
            if "\x00" in content[:8192]:
                continue

            for line_number, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{entry.path}:{line_number}: {_truncate_line(line)}")
                    if len(matches) >= bounded_max:
                        break
            if len(matches) >= bounded_max:
                break

        lines = [
            f"Grep pattern: {pattern}",
            f"Base path: {virtual_path}",
        ]
        if glob_pattern:
            lines.append(f"File filter: {glob_pattern}")

        if matches:
            lines.append(f"Matches ({len(matches)}):")
            lines.extend(matches)
        else:
            lines.append("No matches found.")

        if len(matches) >= bounded_max:
            lines.append(f"... results truncated to {bounded_max} matches")
        return _truncate_tool_output("\n".join(lines))
    except re.error as exc:
        return f"Error searching pattern: invalid regex ({exc})"
    except Exception as exc:
        return f"Error searching pattern: {exc}"
