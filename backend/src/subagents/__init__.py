"""Subagents module initialization."""

from .registry import SubagentConfig as SubagentTypeConfig, SubagentRegistry
from .task_tool import task_tool
from .parallel import ParallelExecutor, ExecutionPhase, PhasedPlan, PhaseResult
from .models import SubagentStatus, SubagentTask, SubagentEvent, SubagentResult
from .config import SubagentConfig
from .manager import ThreadContext, GlobalSubagentManager
from .graph import GraphTemplateRegistry, create_academic_agent_graph, register_academic_templates

# Academic subagents
from .academic import (
    AcademicAgentResolver,
    AcademicAgentError,
    UnknownSubagentTypeError,
    InvalidToolError,
    SCOUT_PROMPT,
    WRITER_PROMPT,
    SYNTHESIZER_PROMPT,
    ANALYST_PROMPT,
)

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
