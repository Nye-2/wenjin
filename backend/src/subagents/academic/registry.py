"""Academic subagent registry for managing subagent configurations.

This module provides the SubagentConfig dataclass and registry functions
for the four specialized academic subagents: Scout, Writer, Synthesizer,
and Analyst.
"""

from dataclasses import dataclass, field

from .prompts import (
    ANALYST_PROMPT,
    SCOUT_PROMPT,
    SYNTHESIZER_PROMPT,
    WRITER_PROMPT,
)
from .thesis_prompts import (
    FIGURE_PLANNER_PROMPT,
    LIBRARIAN_PROMPT,
    THESIS_WRITER_PROMPT,
)


@dataclass
class SubagentConfig:
    """Configuration for a subagent type.

    Attributes:
        name: Human-readable name of the subagent
        description: Brief description of the subagent's purpose
        system_prompt: System prompt for the subagent
        tools: List of tool names available to this subagent
        max_turns: Maximum number of turns for the subagent
    """
    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    max_turns: int = 10


# Subagent configurations
SCOUT_CONFIG = SubagentConfig(
    name="Scout",
    description="Literature exploration agent for discovering academic papers",
    system_prompt=SCOUT_PROMPT,
    tools=["semantic_scholar_search"],
    max_turns=10,
)

WRITER_CONFIG = SubagentConfig(
    name="Writer",
    description="Academic writing agent for producing high-quality content",
    system_prompt=WRITER_PROMPT,
    tools=["get_paper_section", "get_paper_toc"],
    max_turns=15,
)

SYNTHESIZER_CONFIG = SubagentConfig(
    name="Synthesizer",
    description="Knowledge synthesis agent for generating insights and finding gaps",
    system_prompt=SYNTHESIZER_PROMPT,
    tools=["get_paper_section", "get_paper_toc"],
    max_turns=10,
)

ANALYST_CONFIG = SubagentConfig(
    name="Analyst",
    description="Data analysis agent for methodology review and analysis",
    system_prompt=ANALYST_PROMPT,
    tools=["get_paper_section"],
    max_turns=10,
)

THESIS_WRITER_CONFIG = SubagentConfig(
    name="ThesisWriter",
    description="Undergraduate thesis writing expert for producing complete thesis sections",
    system_prompt=THESIS_WRITER_PROMPT,
    tools=["read_file", "write_file", "str_replace", "task"],
    max_turns=15,
)

LIBRARIAN_CONFIG = SubagentConfig(
    name="Librarian",
    description="Academic literature search and citation planning expert",
    system_prompt=LIBRARIAN_PROMPT,
    tools=["semantic_scholar_search", "read_file"],
    max_turns=10,
)

FIGURE_PLANNER_CONFIG = SubagentConfig(
    name="FigurePlanner",
    description="Academic illustration planning expert for thesis figures",
    system_prompt=FIGURE_PLANNER_PROMPT,
    tools=["read_file"],
    max_turns=8,
)


# Registry dictionary
SUBAGENT_REGISTRY: dict[str, SubagentConfig] = {
    "scout": SCOUT_CONFIG,
    "writer": WRITER_CONFIG,
    "synthesizer": SYNTHESIZER_CONFIG,
    "analyst": ANALYST_CONFIG,
    "thesis_writer": THESIS_WRITER_CONFIG,
    "librarian": LIBRARIAN_CONFIG,
    "figure_planner": FIGURE_PLANNER_CONFIG,
}


def get_subagent_config(subagent_type: str) -> SubagentConfig:
    """Get subagent configuration by type.

    Args:
        subagent_type: Type identifier (e.g., 'scout', 'writer')

    Returns:
        SubagentConfig for the requested type

    Raises:
        ValueError: If the subagent type is not found
    """
    if subagent_type not in SUBAGENT_REGISTRY:
        raise ValueError(f"Unknown subagent type: {subagent_type}")
    return SUBAGENT_REGISTRY[subagent_type]


def get_all_subagent_types() -> list[str]:
    """Get all available subagent types.

    Returns:
        List of subagent type identifiers
    """
    return list(SUBAGENT_REGISTRY.keys())
