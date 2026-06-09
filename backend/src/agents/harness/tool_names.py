"""Canonical harness tool-name helpers."""

from __future__ import annotations

from collections.abc import Iterable

CANONICAL_TOOL_ALIASES = {
    "sandbox_python": "sandbox.run_python",
    "sandbox_exec": "sandbox.run_python",
}

READ_OUTPUT_REF_TOOL = "sandbox.read_output_ref"
READ_FILE_TOOL = "sandbox.read_file"


def canonical_tool_name(name: str) -> str:
    text = str(name).strip()
    return CANONICAL_TOOL_ALIASES.get(text, text)


def expand_tool_names(names: Iterable[str] | None) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in names or ():
        name = canonical_tool_name(str(raw))
        for expanded in _tool_with_companion(name):
            if expanded and expanded not in seen:
                seen.add(expanded)
                result.append(expanded)
    return tuple(result)


def _tool_with_companion(tool_name: str) -> tuple[str, ...]:
    if tool_name == READ_FILE_TOOL:
        return (READ_FILE_TOOL, READ_OUTPUT_REF_TOOL)
    return (tool_name,)
