"""Public tool helpers without import-time runtime assembly.

ToolOrchestrator is infrastructure and must be importable without loading the
agent graph or every built-in tool. Built-ins remain lazily available to the
few callers that import them from this package.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_BUILTIN_EXPORTS = {"ask_clarification_tool", "present_files_tool"}

__all__ = sorted(_BUILTIN_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _BUILTIN_EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module("src.tools.builtins"), name)
    globals()[name] = value
    return value
