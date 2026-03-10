"""Graph template registry for subagent graphs."""

from typing import Any, Optional


class GraphTemplateRegistry:
    """Registry for graph templates used by subagents."""

    def __init__(self):
        """Initialize an empty registry."""
        self._templates: dict[str, Any] = {}

    @property
    def count(self) -> int:
        """Return the number of registered templates."""
        return len(self._templates)

    def register(self, name: str, graph: Any) -> None:
        """Register a graph template.

        Args:
            name: Template name
            graph: Graph object to register
        """
        self._templates[name] = graph

    def get(self, name: str) -> Optional[Any]:
        """Get a registered graph template.

        Args:
            name: Template name

        Returns:
            Graph object if found, None otherwise
        """
        return self._templates.get(name)

    def has(self, name: str) -> bool:
        """Check if a template is registered.

        Args:
            name: Template name

        Returns:
            True if registered, False otherwise
        """
        return name in self._templates


def create_default_subagent_graph(llm: Any, tools: list, max_turns: int = 10) -> Any:
    """Create a default ReAct-style subagent graph.

    Args:
        llm: Language model instance
        tools: List of tools available to the agent
        max_turns: Maximum number of turns (default: 10)

    Returns:
        A compiled LangGraph agent

    Raises:
        ImportError: If langgraph is not installed
    """
    try:
        from langgraph.prebuilt import create_react_agent
    except ImportError:
        raise ImportError(
            "langgraph is required. Install with: pip install langgraph"
        )

    return create_react_agent(llm, tools=tools)
