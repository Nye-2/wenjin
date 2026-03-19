"""Subagents module initialization."""

# Academic subagents
from .academic import (
    ANALYST_PROMPT,
    SCOUT_PROMPT,
    SYNTHESIZER_PROMPT,
    WRITER_PROMPT,
    AcademicAgentError,
    AcademicAgentResolver,
    InvalidToolError,
    UnknownSubagentTypeError,
)
from .config import SubagentConfig
from .graph import GraphTemplateRegistry, create_academic_agent_graph, register_academic_templates
from .manager import GlobalSubagentManager, ThreadContext
from .models import SubagentEvent, SubagentResult, SubagentStatus, SubagentTask
from .parallel import ExecutionPhase, ParallelExecutor, PhasedPlan, PhaseResult
from .registry import SubagentConfig as SubagentTypeConfig
from .registry import SubagentRegistry
from .task_tool import task_tool

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
    "ThreadContext",
    "GlobalSubagentManager",
    # Graph templates
    "GraphTemplateRegistry",
    "create_academic_agent_graph",
    "register_academic_templates",
    # Academic subagents
    "AcademicAgentResolver",
    "AcademicAgentError",
    "UnknownSubagentTypeError",
    "InvalidToolError",
    "SCOUT_PROMPT",
    "WRITER_PROMPT",
    "SYNTHESIZER_PROMPT",
    "ANALYST_PROMPT",
]
