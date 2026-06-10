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
    needs_output_ref_reader = False
    for raw in names or ():
        name = canonical_tool_name(str(raw))
        if not name:
            continue
        if name in {READ_FILE_TOOL, "sandbox.run_python"}:
            needs_output_ref_reader = True
        if name not in seen:
            seen.add(name)
            result.append(name)
    if needs_output_ref_reader and READ_OUTPUT_REF_TOOL not in seen:
        result.append(READ_OUTPUT_REF_TOOL)
    return tuple(result)
