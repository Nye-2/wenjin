"""Graph template registry for subagent graphs."""

import threading
from typing import Any


def build_subagent_tool_middlewares() -> list[Any]:
    """Build tool middlewares that are safe for subagent runtime use."""
    middlewares: list[Any] = []

    try:
        from src.agents.middlewares.execution import ExecutionMiddleware
        from src.thesis.execution import get_execution_service

        execution_service = get_execution_service()
    except Exception:
        execution_service = None

    if execution_service is not None:
        middlewares.append(ExecutionMiddleware(execution_service))

    return middlewares


def _create_subagent_react_agent(
    llm: Any,
    tools: list,
    *,
    system_prompt: str | None = None,
) -> Any:
    """Create a subagent react graph with middleware-aware tools."""
    from langgraph.prebuilt import create_react_agent

    from src.agents.lead_agent.dynamic_tools import DynamicToolNode

    fixed_tools = list(tools or [])
    tool_node = DynamicToolNode(
        lambda: fixed_tools,
        middlewares=build_subagent_tool_middlewares(),
    )

    def _resolve_model(_state, _runtime):
        current_tools = tool_node.list_available_tools()
        if not current_tools:
            return llm
        return llm.bind_tools(current_tools)

    kwargs: dict[str, Any] = {}
    if system_prompt:
        kwargs["prompt"] = system_prompt

    return create_react_agent(_resolve_model, tool_node, **kwargs)


class GraphTemplateRegistry:
    """Registry for graph templates used by subagents."""

    def __init__(self):
        """Initialize an empty registry."""
        self._templates: dict[str, Any] = {}
        self._lock = threading.Lock()

    @property
    def count(self) -> int:
        """Return the number of registered templates."""
        with self._lock:
            return len(self._templates)

    def register(self, name: str, graph: Any) -> None:
        """Register a graph template.

        Args:
            name: Template name.
            graph: Graph object to register.
        """
        with self._lock:
            self._templates[name] = graph

    def get(self, name: str) -> Any | None:
        """Get a registered graph template.

        Args:
            name: Template name.

        Returns:
            Graph object if found, None otherwise.
        """
        with self._lock:
            return self._templates.get(name)

    def has(self, name: str) -> bool:
        """Check if a template is registered.

        Args:
            name: Template name.

        Returns:
            True if registered, False otherwise.
        """
        with self._lock:
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
        return _create_subagent_react_agent(llm, tools)
    except ImportError as exc:
        raise ImportError(
            "langgraph is required. Install with: pip install langgraph"
        ) from exc


def create_academic_agent_graph(
    llm: Any,
    tools: list,
    system_prompt: str,
    max_turns: int = 10,
) -> Any:
    """Create a ReAct agent with custom system prompt for academic tasks.

    Args:
        llm: Language model instance
        tools: List of tools available to the agent
        system_prompt: Custom system prompt for the academic agent
        max_turns: Maximum number of turns (default: 10)

    Returns:
        A compiled LangGraph agent with custom system prompt

    Raises:
        ImportError: If langgraph is not installed
    """
    try:
        return _create_subagent_react_agent(
            llm,
            tools,
            system_prompt=system_prompt,
        )
    except ImportError as exc:
        raise ImportError(
            "langgraph is required. Install with: pip install langgraph"
        ) from exc


def register_academic_templates(
    registry: GraphTemplateRegistry,
    llm: Any,
    tools: dict
) -> None:
    """Register academic agent graph templates.

    Args:
        registry: GraphTemplateRegistry instance
        llm: Language model instance
        tools: Dictionary of available tools
    """
    from src.subagents.academic import get_all_subagent_types, get_subagent_config

    for agent_type in get_all_subagent_types():
        config = get_subagent_config(agent_type)
        # Filter tools to only those available
        agent_tools = [tools[t] for t in config.tools if t in tools]
        graph = create_academic_agent_graph(
            llm,
            agent_tools,
            config.system_prompt,
            max_turns=config.max_turns
        )
        registry.register(f"academic_{agent_type}", graph)
