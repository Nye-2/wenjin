"""Subagents module initialization."""

from .registry import SubagentConfig, SubagentRegistry
from .task_tool import task_tool

__all__ = ["SubagentRegistry", "SubagentConfig", "task_tool"]
