"""Subagents module initialization."""

from .registry import SubagentRegistry, SubagentConfig
from .task_tool import task_tool

__all__ = ["SubagentRegistry", "SubagentConfig", "task_tool"]
