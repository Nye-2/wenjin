"""Subagent v2 package — base classes and registry."""

from .base import SubagentBase, SubagentContext, SubagentResult
from .registry import REGISTRY, subagent

__all__ = [
    "SubagentBase",
    "SubagentContext",
    "SubagentResult",
    "REGISTRY",
    "subagent",
]
