"""Subagent v2 registry — maps string names to SubagentBase subclasses."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import SubagentBase


class _Registry:
    """Simple name-to-class registry for v2 subagents."""

    def __init__(self) -> None:
        self._d: dict[str, type[SubagentBase]] = {}

    def register(self, name: str, cls: type[SubagentBase]) -> None:
        """Register a subagent class under the given name.

        Also sets cls.name = name so the class knows its own registration key.
        """
        self._d[name] = cls
        cls.name = name

    def get(self, name: str) -> type[SubagentBase]:
        """Retrieve a registered subagent class by name.

        Raises:
            KeyError: If no subagent is registered under that name.
        """
        if name not in self._d:
            raise KeyError(f"subagent '{name}' not registered")
        return self._d[name]

    def all_names(self) -> list[str]:
        """Return all registered subagent names."""
        return list(self._d.keys())


#: Global singleton registry — import this to register or look up subagents.
REGISTRY = _Registry()


def subagent(name: str):
    """Class decorator that registers a SubagentBase subclass in the global REGISTRY.

    Usage::

        @subagent("scholar_searcher")
        class ScholarSearcher(SubagentBase):
            ...
    """

    def decorator(cls):
        REGISTRY.register(name, cls)
        return cls

    return decorator
