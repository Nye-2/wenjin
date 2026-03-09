"""Subagents module initialization."""

from .registry import SubagentConfig, SubagentRegistry
from .task_tool import task_tool
from .parallel import ParallelExecutor, ExecutionPhase, PhasedPlan, PhaseResult

__all__ = [
    "SubagentRegistry",
    "SubagentConfig",
    "task_tool",
    "ParallelExecutor",
    "ExecutionPhase",
    "PhasedPlan",
    "PhaseResult",
]
