"""Subagents module initialization."""

from .registry import SubagentConfig as SubagentTypeConfig, SubagentRegistry
from .task_tool import task_tool
from .parallel import ParallelExecutor, ExecutionPhase, PhasedPlan, PhaseResult
from .models import SubagentStatus, SubagentTask, SubagentEvent, SubagentResult
from .config import SubagentConfig

__all__ = [
    "SubagentRegistry",
    "SubagentTypeConfig",  # Legacy: Subagent type configuration (dataclass)
    "SubagentConfig",      # New: System configuration (Pydantic)
    "SubagentStatus",
    "SubagentTask",
    "SubagentEvent",
    "SubagentResult",
    "task_tool",
    "ParallelExecutor",
    "ExecutionPhase",
    "PhasedPlan",
    "PhaseResult",
]
