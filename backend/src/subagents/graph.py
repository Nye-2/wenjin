"""Graph template registry for subagent graphs."""

import threading
from collections import OrderedDict
from typing import Any, cast


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
    tools: list[Any],
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

    def _resolve_model(_state: object, _runtime: object) -> Any:
        current_tools = tool_node.list_available_tools()
        if not current_tools:
            return llm
        return llm.bind_tools(current_tools)

    kwargs: dict[str, Any] = {}
    if system_prompt:
        kwargs["prompt"] = system_prompt

    return cast(Any, create_react_agent)(_resolve_model, tool_node, **kwargs)


class GraphTemplateRegistry:
    """LRU-evicting registry for compiled subagent graph templates.

    Prevents unbounded memory growth by evicting the least-recently-used
    entry when the registry reaches max_size.
    """

    def __init__(self, max_size: int = 50) -> None:
        """Initialize with a size cap.

        Args:
            max_size: Maximum number of graphs to keep. The LRU entry is
                      evicted when this limit is reached. Default: 50.
        """
        if max_size < 1:
            raise ValueError(f"max_size must be >= 1, got {max_size}")
        self._templates: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    @property
    def max_size(self) -> int:
        """Return the configured maximum registry size."""
        return self._max_size

    @property
    def count(self) -> int:
        """Return the number of registered templates."""
        with self._lock:
            return len(self._templates)

    def register(self, name: str, graph: Any) -> None:
        """Register a graph template, evicting the LRU entry if at capacity.

        Args:
            name: Cache key.
            graph: Compiled LangGraph object.
        """
        with self._lock:
            if name in self._templates:
                self._templates.move_to_end(name)  # promote to MRU
            elif len(self._templates) >= self._max_size:
                self._templates.popitem(last=False)  # evict LRU
            self._templates[name] = graph  # insert or update value in both cases

    def get(self, name: str) -> Any | None:
        """Get a registered template and mark it as recently used."""
        with self._lock:
            if name not in self._templates:
                return None
            self._templates.move_to_end(name)
            return self._templates[name]

    def has(self, name: str) -> bool:
        """Check if a template is registered.

        Note: unlike ``get()``, this method does **not** promote the entry to
        most-recently-used. Use ``get()`` when you intend to access the graph.

        Args:
            name: Template name.

        Returns:
            True if registered, False otherwise.
        """
        with self._lock:
            return name in self._templates


def create_default_subagent_graph(llm: Any, tools: list[Any], max_turns: int = 10) -> Any:
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
    tools: list[Any],
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
    tools: dict[str, Any],
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
