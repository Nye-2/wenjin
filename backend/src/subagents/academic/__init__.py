"""Academic subagents module.

This module provides specialized academic subagents:
- Scout: Literature exploration and citation chain tracking
- Writer: Academic writing following discipline norms
- Synthesizer: Insight generation and gap finding
- Analyst: Data analysis and methodology review
"""

from .errors import (
    AcademicAgentError,
    InvalidToolError,
    UnknownSubagentTypeError,
)
from .prompts import (
    ANALYST_PROMPT,
    SCOUT_PROMPT,
    SYNTHESIZER_PROMPT,
    WRITER_PROMPT,
)
from .registry import (
    SUBAGENT_REGISTRY,
    SubagentConfig,
    get_all_subagent_types,
    get_subagent_config,
)
from .resolver import AcademicAgentResolver
from .thesis_prompts import (
    FIGURE_PLANNER_PROMPT,
    LIBRARIAN_PROMPT,
    THESIS_WRITER_PROMPT,
)

__all__ = [
    # Errors
    "AcademicAgentError",
    "InvalidToolError",
    "UnknownSubagentTypeError",
    # Prompts
    "SCOUT_PROMPT",
    "WRITER_PROMPT",
    "SYNTHESIZER_PROMPT",
    "ANALYST_PROMPT",
    "THESIS_WRITER_PROMPT",
    "LIBRARIAN_PROMPT",
    "FIGURE_PLANNER_PROMPT",
    # Registry
    "SubagentConfig",
    "SUBAGENT_REGISTRY",
    "get_subagent_config",
    "get_all_subagent_types",
    # Resolver
    "AcademicAgentResolver",
]
