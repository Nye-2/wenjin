"""Academic subagents module.

This module provides specialized academic subagents:
- Scout: Literature exploration and citation chain tracking
- Writer: Academic writing following discipline norms
- Synthesizer: Insight generation and gap finding
- Analyst: Data analysis and methodology review
"""

from .prompts import (
    SCOUT_PROMPT,
    WRITER_PROMPT,
    SYNTHESIZER_PROMPT,
    ANALYST_PROMPT,
)
from .registry import (
    SubagentConfig,
    SUBAGENT_REGISTRY,
    get_subagent_config,
    get_all_subagent_types,
)

__all__ = [
    # Prompts
    "SCOUT_PROMPT",
    "WRITER_PROMPT",
    "SYNTHESIZER_PROMPT",
    "ANALYST_PROMPT",
    # Registry
    "SubagentConfig",
    "SUBAGENT_REGISTRY",
    "get_subagent_config",
    "get_all_subagent_types",
]
