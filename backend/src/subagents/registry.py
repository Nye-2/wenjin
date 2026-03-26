"""Compatibility wrapper around the canonical academic subagent registry."""

from src.subagents.academic.registry import (
    DEFAULT_SUBAGENTS,
    SUBAGENT_REGISTRY,
    SubagentConfig,
    SubagentRegistry,
    get_all_subagent_types,
    get_subagent_config,
    registry,
)

__all__ = [
    "SubagentConfig",
    "SubagentRegistry",
    "DEFAULT_SUBAGENTS",
    "SUBAGENT_REGISTRY",
    "registry",
    "get_subagent_config",
    "get_all_subagent_types",
]
