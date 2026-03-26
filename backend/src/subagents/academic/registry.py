"""Canonical academic subagent registry.

This module is the single source of truth for subagent type definitions.
Legacy imports from ``src.subagents.registry`` are compatibility aliases that
re-export the data structures defined here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from .prompts import (
    ANALYST_PROMPT,
    GAP_MINER_PROMPT,
    REVIEWER_PROMPT,
    SCOUT_PROMPT,
    SYNTHESIZER_PROMPT,
    TREND_SPOTTER_PROMPT,
    WRITER_PROMPT,
)
from .thesis_prompts import (
    FIGURE_PLANNER_PROMPT,
    LIBRARIAN_PROMPT,
    THESIS_WRITER_PROMPT,
)


def _normalize_tool_names(tool_names: Iterable[str] | None) -> list[str]:
    """Normalize tool lists while preserving order."""
    normalized: list[str] = []
    seen: set[str] = set()

    for raw_name in tool_names or ():
        name = str(raw_name).strip()
        if not name or name in seen:
            continue
        normalized.append(name)
        seen.add(name)

    return normalized


def _normalize_subagent_type(subagent_type: str) -> str:
    """Normalize subagent identifiers to the canonical registry key shape."""
    return str(subagent_type).strip().lower().replace("-", "_").replace(" ", "_")


@dataclass
class SubagentConfig:
    """Configuration for a subagent type."""

    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    max_turns: int = 10

    def __post_init__(self) -> None:
        self.tools = _normalize_tool_names(self.tools)
        self.disallowed_tools = _normalize_tool_names(self.disallowed_tools)

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        """Compatibility alias used by legacy executor code."""
        return tuple(self.tools)

    def copy_with(
        self,
        *,
        tools: Iterable[str] | None = None,
        disallowed_tools: Iterable[str] | None = None,
        max_turns: int | None = None,
    ) -> SubagentConfig:
        """Return a copied config with selected overrides applied."""
        return replace(
            self,
            tools=list(self.tools if tools is None else tools),
            disallowed_tools=list(
                self.disallowed_tools if disallowed_tools is None else disallowed_tools
            ),
            max_turns=self.max_turns if max_turns is None else max_turns,
        )


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

GAP_MINER_CONFIG = SubagentConfig(
    name="Gap Miner",
    description="Research gap identification agent",
    system_prompt=GAP_MINER_PROMPT,
    tools=["read_file"],
    max_turns=8,
)

TREND_SPOTTER_CONFIG = SubagentConfig(
    name="Trend Spotter",
    description="Research trend analysis agent",
    system_prompt=TREND_SPOTTER_PROMPT,
    tools=["semantic_scholar_search", "web_search"],
    max_turns=8,
)

REVIEWER_CONFIG = SubagentConfig(
    name="Reviewer",
    description="Academic review and feedback agent",
    system_prompt=REVIEWER_PROMPT,
    tools=["read_file"],
    max_turns=8,
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


DEFAULT_SUBAGENTS: dict[str, SubagentConfig] = {
    "scout": SCOUT_CONFIG,
    "writer": WRITER_CONFIG,
    "synthesizer": SYNTHESIZER_CONFIG,
    "analyst": ANALYST_CONFIG,
    "gap_miner": GAP_MINER_CONFIG,
    "trend_spotter": TREND_SPOTTER_CONFIG,
    "reviewer": REVIEWER_CONFIG,
    "thesis_writer": THESIS_WRITER_CONFIG,
    "librarian": LIBRARIAN_CONFIG,
    "figure_planner": FIGURE_PLANNER_CONFIG,
}


class SubagentRegistry:
    """Registry for canonical subagent configurations."""

    def __init__(self, subagents: Mapping[str, SubagentConfig] | None = None):
        self._subagents: dict[str, SubagentConfig] = {}
        for subagent_type, config in (subagents or {}).items():
            self.register(subagent_type, config)

    def get(self, subagent_type: str) -> SubagentConfig | None:
        """Return a copied config if the type exists."""
        config = self._subagents.get(_normalize_subagent_type(subagent_type))
        return config.copy_with() if config is not None else None

    def require(self, subagent_type: str) -> SubagentConfig:
        """Return a config or raise if the type does not exist."""
        config = self.get(subagent_type)
        if config is None:
            raise ValueError(f"Unknown subagent type: {subagent_type}")
        return config

    def list_all(self) -> list[SubagentConfig]:
        """Return copied configs for all registered subagents."""
        return [config.copy_with() for config in self._subagents.values()]

    def list_types(self) -> list[str]:
        """Return registered subagent identifiers."""
        return sorted(self._subagents.keys())

    def register(
        self,
        subagent_type: str | SubagentConfig,
        config: SubagentConfig | None = None,
    ) -> None:
        """Register a config by explicit key or by normalized config name."""
        if isinstance(subagent_type, SubagentConfig):
            normalized_type = _normalize_subagent_type(subagent_type.name)
            config_to_store = subagent_type
        elif config is not None:
            normalized_type = _normalize_subagent_type(subagent_type)
            config_to_store = config
        else:
            raise TypeError("register() requires a config instance")

        self._subagents[normalized_type] = config_to_store.copy_with()

    def unregister(self, subagent_type: str) -> bool:
        """Remove a registered config if present."""
        normalized_type = _normalize_subagent_type(subagent_type)
        if normalized_type not in self._subagents:
            return False
        del self._subagents[normalized_type]
        return True


registry = SubagentRegistry(DEFAULT_SUBAGENTS)

# Legacy export name used by existing imports. Expose a read-only live view so
# compatibility callers cannot mutate canonical registry state by accident.
SUBAGENT_REGISTRY = MappingProxyType(registry._subagents)


def get_subagent_config(subagent_type: str) -> SubagentConfig:
    """Get subagent configuration by type."""
    return registry.require(subagent_type)


def get_all_subagent_types() -> list[str]:
    """Get all available subagent types."""
    return registry.list_types()
