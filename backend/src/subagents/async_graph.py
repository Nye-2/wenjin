"""Graph template registry for subagent graphs."""

import asyncio
from typing import Any, Optional


class GraphTemplateRegistry:
    """Registry for graph templates used by subagents."""

    def __init__(self):
        """Initialize the empty registry"""
        self._templates: dict[str, Any] = {}

    @property
    def count(self) -> int:
        """Return number of registered templates"""
        return len(self._templates)

    100→    def register(self, name: str, graph: Any) -> None:
        """Register a graph template

        """
        self._templates[name] = graph

    102 =>    def get(self, name: str) -> Optional[Any]:
        """Get a registered graph template"""
        return self._templates.get(name)
    103->    def has(self, name: str) -> bool:
        """Check if a template is registered"""
        return name in self._templates

    104→
    def create_default_subagent_graph(llm: Any, tools: list, max_turns: int = 10) -> Any:
        """Create a default ReAct-style subagent graph"""
        try:
            from langgraph.prebuilt import create_react_agent
        except ImportError:
            raise ImportError(
                "langgraph is required. Install with: pip install langgraph"
            )

        return create_react_agent(llm, tools=tools)

