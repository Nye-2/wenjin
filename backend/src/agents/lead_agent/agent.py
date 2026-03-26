"""Lead Agent factory for AcademiaGPT."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from src.agents.lead_agent.chat_skill_catalog import list_workspace_chat_skills
from src.agents.lead_agent.dynamic_tools import DynamicToolNode
from src.agents.middlewares import (
    CitationContextMiddleware,
    ClarificationMiddleware,
    DanglingToolCallMiddleware,
    DisciplineContextMiddleware,
    ExecutionMiddleware,
    KnowledgeContextMiddleware,
    LiteratureContextMiddleware,
    MemoryMiddleware,
    SandboxMiddleware,
    SubagentLimitMiddleware,
    SummarizationMiddleware,
    ThreadDataMiddleware,
    TitleMiddleware,
    TodoListMiddleware,
    UploadsMiddleware,
    ViewImageMiddleware,
    WorkspaceContextMiddleware,
)
from src.agents.thread_state import ThreadState
from src.config import get_default_model_id, get_model_config
from src.config.config_loader import get_app_config
from src.sandbox.runtime import get_sandbox_provider

logger = logging.getLogger(__name__)


def _model_supports_vision(model_name: str | None) -> bool:
    """Infer whether the configured model can accept image inputs."""
    if not model_name:
        return False

    try:
        model_config = get_model_config(model_name)
    except Exception:
        model_config = None

    raw_model = (getattr(model_config, "model", None) or model_name).lower()
    return any(tag in raw_model for tag in ("vision", "vl", "gpt-4o"))


def _default_subagent_enabled() -> bool:
    """Resolve the default subagent toggle from app config."""
    try:
        return bool(get_app_config().subagents.enabled)
    except Exception:
        return True


def _default_model_name() -> str:
    """Resolve the default model id used by the lead agent."""
    try:
        return get_default_model_id()
    except Exception:
        return "default"


def _normalize_runtime_config(config: RunnableConfig | None) -> RunnableConfig:
    """Fill runtime defaults expected by the middleware/tool stack."""
    normalized = dict(config or {})
    configurable = dict(normalized.get("configurable", {}))

    configurable["model_name"] = configurable.get("model_name") or _default_model_name()
    configurable.setdefault("subagent_enabled", _default_subagent_enabled())
    if configurable.get("supports_vision") is None:
        configurable.pop("supports_vision", None)
    configurable.setdefault("supports_vision", _model_supports_vision(configurable["model_name"]))

    normalized["configurable"] = configurable
    return normalized


def _merge_runtime_config(
    base: RunnableConfig | None,
    override: RunnableConfig | None,
) -> RunnableConfig:
    """Merge a default runtime config with a request-specific override."""
    if base is None and override is None:
        return {}
    if base is None:
        return dict(override or {})
    if override is None:
        return dict(base)

    merged = {**base, **override}
    base_configurable = dict(base.get("configurable", {}))
    override_configurable = dict(override.get("configurable", {}))
    merged_configurable = {
        **base_configurable,
        **override_configurable,
    }
    if (
        "model_name" in override_configurable
        and "supports_vision" not in override_configurable
    ):
        merged_configurable.pop("supports_vision", None)
    elif override_configurable.get("supports_vision") is None:
        merged_configurable.pop("supports_vision", None)

    merged["configurable"] = merged_configurable
    return merged


def _render_workspace_available_skills(workspace_type: str | None) -> str:
    skills = list_workspace_chat_skills(workspace_type)
    if not skills:
        return ""
    lines = [
        "\n\n## Available Skills",
        "Use these skills for specific academic tasks:",
    ]
    lines.extend(f"- {skill.id}: {skill.description}" for skill in skills)
    return "\n".join(lines)


def _extend_unique_tools(
    existing: list[BaseTool],
    new_tools: list[BaseTool],
) -> None:
    """Append tools while deduplicating by tool name."""
    seen_names = {
        tool.name
        for tool in existing
        if getattr(tool, "name", None)
    }

    for tool in new_tools:
        tool_name = getattr(tool, "name", None)
        if tool_name and tool_name in seen_names:
            continue
        if tool_name:
            seen_names.add(tool_name)
        existing.append(tool)


def apply_prompt_template(
    state: ThreadState,
    config: RunnableConfig,
) -> str:
    """Apply prompt template with academic context.

    Args:
        state: Current thread state
        config: Runtime configuration

    Returns:
        System prompt string
    """
    # Base system prompt
    base_prompt = """You are AcademiaGPT, an expert academic research and writing assistant.

You help researchers with:
- Literature research and analysis
- Research idea generation and refinement
- Academic paper writing (SCI papers, theses, proposals)
- Methodology design and experimental planning
- Citation management and formatting

## Capabilities

You have access to specialized tools and subagents for:
1. **Literature Search**: Search external databases (Semantic Scholar, arXiv, Crossref, OpenAlex)
2. **Paper Navigation**: Browse papers by their table of contents (TOC) structure
3. **Subagent Delegation**: Delegate complex tasks to specialized agents

## Guidelines

- Always cite sources when making claims
- Follow academic writing standards appropriate to the discipline
- Be thorough but concise
- Ask for clarification when needed"""

    # Add workspace context
    workspace_type = state.get("workspace_type")
    discipline = state.get("discipline")

    if workspace_type:
        type_labels = {
            "sci": "SCI Paper",
            "thesis": "Thesis / Dissertation",
            "proposal": "Research Proposal",
            "software_copyright": "Software Copyright Application",
            "patent": "Patent Application",
        }
        base_prompt += f"\n\n## Current Project\nProject Type: {type_labels.get(workspace_type, workspace_type)}"

    if discipline:
        base_prompt += f"\nDiscipline: {discipline.replace('_', ' ').title()}"

    # Add literature context
    literature_context = state.get("literature_context", "")
    if literature_context:
        base_prompt += f"\n\n{literature_context}"

    # Add long-term user memory context
    memory_context = state.get("memory_context", "")
    if memory_context:
        base_prompt += f"\n\n{memory_context}"

    # Add knowledge context
    knowledge_context = state.get("knowledge_context", "")
    if knowledge_context:
        base_prompt += f"\n\n{knowledge_context}"

    # Add discipline norms
    discipline_norms = state.get("discipline_norms", {})
    if discipline_norms:
        base_prompt += "\n\n## Writing Guidelines"
        if "citation_style" in discipline_norms:
            base_prompt += f"\n- Citation Style: {discipline_norms['citation_style']}"
        if "writing_style" in discipline_norms:
            base_prompt += f"\n- Writing Style: {discipline_norms['writing_style']}"
        if "structure" in discipline_norms:
            base_prompt += f"\n- Paper Structure: {' → '.join(discipline_norms['structure'])}"

    configurable = config.get("configurable", {})
    selected_skill = (
        configurable.get("selected_skill")
        or state.get("current_skill")
    )
    if selected_skill:
        base_prompt += (
            "\n\n## Preferred Skill"
            f"\nThe user selected `{selected_skill}` for this turn."
            "\nUse it as the default approach unless the request clearly requires a different toolchain."
        )

    thread_id = configurable.get("thread_id")
    workspace_id = configurable.get("workspace_id")
    user_id = configurable.get("user_id")
    if workspace_id or thread_id or user_id:
        base_prompt += "\n\n## Runtime Context"
        if workspace_id:
            base_prompt += f"\n- Workspace ID: {workspace_id}"
        if thread_id:
            base_prompt += f"\n- Thread ID: {thread_id}"
        if user_id:
            base_prompt += f"\n- User ID: {user_id}"
        base_prompt += (
            "\nUse these ids when calling workspace tools."
            "\nPrefer `run_workspace_feature` for deterministic feature execution."
        )

    base_prompt += _render_workspace_available_skills(workspace_type)

    return base_prompt


def get_available_tools(
    groups: list[str] | None = None,
    include_mcp: bool = True,
    include_execution: bool = False,
    model_name: str | None = None,
    subagent_enabled: bool = True,
) -> list[BaseTool]:
    """Get available tools based on configuration.

    Args:
        groups: Tool groups to include (None = all)
        include_mcp: Include MCP tools
        include_execution: Include execution tools that require tool middleware
        model_name: Model name for model-specific tools
        subagent_enabled: Include subagent delegation tool

    Returns:
        List of tools
    """
    tools: list[BaseTool] = []

    # Import built-in tools
    from src.tools.builtins import (
        ask_clarification_tool,
        bash_tool,
        list_workspace_artifacts_tool,
        list_workspace_features_tool,
        ls_tool,
        present_files_tool,
        read_file_tool,
        run_workspace_feature_tool,
        str_replace_tool,
        view_image_tool,
        write_file_tool,
    )

    # File system tools
    tools.extend([
        bash_tool,
        read_file_tool,
        write_file_tool,
        str_replace_tool,
        ls_tool,
        view_image_tool,
    ])

    # Interaction tools
    tools.append(ask_clarification_tool)
    tools.extend([
        list_workspace_features_tool,
        list_workspace_artifacts_tool,
        run_workspace_feature_tool,
    ])

    # Output tools
    tools.append(present_files_tool)

    if include_execution:
        try:
            from src.tools.execution import get_execution_tools

            _extend_unique_tools(tools, get_execution_tools())
        except ImportError:
            logger.warning("Execution tools unavailable; skipping execution tool registration")
        except Exception as exc:
            logger.error("Failed to load execution tools: %s", exc)

    # Academic tools
    try:
        from src.academic.tools.semantic_scholar import semantic_scholar_search_tool
        tools.append(semantic_scholar_search_tool)
    except ImportError as exc:
        logger.warning(
            "Semantic Scholar tool unavailable; skipping academic search registration: %s",
            exc,
        )
    except Exception as exc:
        logger.error("Failed to load Semantic Scholar tool: %s", exc)

    # Literature navigation tools (TOC-driven)
    # NOTE: These tools require AsyncSession injection (InjectedToolArg) which
    # is not available in the react-agent context. Only include tools whose
    # schemas can be serialized; skip DB-dependent tools to avoid
    # PydanticInvalidForJsonSchema errors.
    try:
        from src.academic.literature.tools import search_external
        tools.append(search_external)
    except ImportError as exc:
        logger.warning(
            "Literature navigation tools unavailable; skipping external search registration: %s",
            exc,
        )
    except Exception as exc:
        logger.error("Failed to load external literature search tool: %s", exc)

    # Citation management tools (skip DB-dependent ones)
    # format_citation and format_bibliography also require AsyncSession injection;
    # they cannot be used in the react-agent context until DB injection is wired.

    if include_mcp:
        try:
            from src.mcp import get_cached_mcp_tools

            _extend_unique_tools(tools, get_cached_mcp_tools())
        except ImportError:
            logger.warning("MCP integration unavailable; skipping MCP tools")
        except Exception as exc:
            logger.error("Failed to load cached MCP tools: %s", exc)

    # Subagent delegation tool
    if subagent_enabled:
        try:
            from src.subagents.task_tool import task_tool
            tools.append(task_tool)
        except ImportError:
            pass

    return tools


def build_middlewares(
    workspace_service=None,
    index_service=None,
    artifact_service=None,
    paper_service=None,
) -> list:
    """Build middleware chain for the agent.

    Order matters! Middlewares execute in order:
    1. WorkspaceContextMiddleware - Load workspace config
    2. LiteratureContextMiddleware - Index-based TOC navigation
    3. KnowledgeContextMiddleware - Load artifacts
    4. DisciplineContextMiddleware - Load discipline norms
    5. CitationContextMiddleware - Track citations (after_model only)

    Args:
        workspace_service: Workspace service instance
        index_service: IndexService instance for literature navigation
        artifact_service: Artifact service instance
        paper_service: Paper service instance

    Returns:
        List of middleware instances
    """
    middlewares = []

    if workspace_service:
        middlewares.append(WorkspaceContextMiddleware(workspace_service))

    if index_service:
        middlewares.append(LiteratureContextMiddleware(index_service))

    if artifact_service:
        middlewares.append(KnowledgeContextMiddleware(artifact_service))

    middlewares.append(DisciplineContextMiddleware())

    if paper_service:
        middlewares.append(CitationContextMiddleware(paper_service))

    return middlewares


def build_pipeline(
    config: dict,
    workspace_service=None,
    index_service=None,
    artifact_service=None,
    paper_service=None,
    sandbox_provider=None,
    memory_queue=None,
) -> list:
    """Build the middleware pipeline for the lead agent.

    Order:
    1.  ThreadDataMiddleware       - Infrastructure
    2.  UploadsMiddleware          - Infrastructure
    3.  SandboxMiddleware          - Infrastructure (new)
    4.  ExecutionMiddleware        - Tool execution routing (conditional)
    5.  DanglingToolCallMiddleware - Fix
    6.  SummarizationMiddleware    - Context management (conditional)
    7.  MemoryMiddleware           - Context management (conditional)
    8.  WorkspaceContextMiddleware - Academic (conditional)
    9.  LiteratureContextMiddleware - Academic (conditional)
    10. KnowledgeContextMiddleware - Academic (conditional)
    11. DisciplineContextMiddleware - Academic
    12. TodoListMiddleware         - Interaction (conditional)
    13. ViewImageMiddleware        - Interaction
    14. SubagentLimitMiddleware    - Control (conditional)
    15. TitleMiddleware            - Post-processing
    16. CitationContextMiddleware  - Post-processing (conditional)
    17. ClarificationMiddleware    - Control (MUST BE LAST)
    """
    config = _normalize_runtime_config(config)
    configurable = config.get("configurable", {})
    is_plan_mode = configurable.get("is_plan_mode", False)
    subagent_enabled = configurable.get("subagent_enabled", _default_subagent_enabled())

    # Get middleware config with error handling
    try:
        app_config = get_app_config()
        mw_config = app_config.middlewares
    except Exception as e:
        logger.warning(f"Failed to load app config, using defaults: {e}")
        # Create a minimal default config
        from types import SimpleNamespace
        mw_config = SimpleNamespace(
            summarization=SimpleNamespace(enabled=False, trigger="tokens:80000", keep="messages:10")
        )
        app_config = SimpleNamespace(middlewares=mw_config, memory=None)

    pipeline = []

    # --- Infrastructure layer (1-3) ---
    pipeline.append(ThreadDataMiddleware())
    pipeline.append(UploadsMiddleware())

    # Sandbox (3) - resolve default provider when sandboxing is configured
    if sandbox_provider is None:
        try:
            sandbox_provider = get_sandbox_provider()
        except Exception as exc:
            logger.warning("Failed to resolve sandbox provider: %s", exc, exc_info=True)
            sandbox_provider = None

    if sandbox_provider:
        pipeline.append(SandboxMiddleware(sandbox_provider))

    # Execution (4) - compile / render tools routed through ExecutionService
    try:
        from src.thesis.execution import get_execution_service

        execution_service = get_execution_service()
    except Exception as exc:
        logger.warning("Failed to resolve execution service: %s", exc)
        execution_service = None

    if execution_service is not None:
        pipeline.append(
            ExecutionMiddleware(
                execution_service,
                paper_service=paper_service,
            )
        )

    # --- Fix layer (5) ---
    pipeline.append(DanglingToolCallMiddleware())

    # --- Context management layer (6-7) ---
    if mw_config.summarization.enabled:
        # Safely parse trigger and keep values
        try:
            trigger_str = getattr(mw_config.summarization, "trigger", "tokens:80000")
            keep_str = getattr(mw_config.summarization, "keep", "messages:10")
            trigger = int(trigger_str.split(":")[1]) if ":" in trigger_str else 80000
            keep = int(keep_str.split(":")[1]) if ":" in keep_str else 10
        except (ValueError, IndexError, AttributeError) as e:
            logger.warning(f"Invalid summarization config, using defaults: {e}")
            trigger, keep = 80000, 10
        pipeline.append(SummarizationMiddleware(trigger_tokens=trigger, keep_messages=keep))

    # Memory (6) - requires queue
    memory_config = getattr(app_config, "memory", None)
    if memory_config and getattr(memory_config, "enabled", False):
        pipeline.append(
            MemoryMiddleware(
                queue=memory_queue,
                enabled=True,
                inject_enabled=getattr(memory_config, "injection_enabled", True),
                capture_enabled=True,
            )
        )

    # --- Academic context layer (8-11) ---
    if workspace_service:
        pipeline.append(WorkspaceContextMiddleware(workspace_service))
    if index_service:
        pipeline.append(LiteratureContextMiddleware(index_service))
    if artifact_service:
        pipeline.append(KnowledgeContextMiddleware(artifact_service))
    pipeline.append(DisciplineContextMiddleware())

    # --- Interaction layer (12-14) ---
    # TodoList (12) - plan mode only
    if is_plan_mode:
        pipeline.append(TodoListMiddleware())

    # ViewImage (13) - always present, handles vision internally
    pipeline.append(ViewImageMiddleware())

    # SubagentLimit (14) - subagents enabled
    if subagent_enabled:
        max_concurrent = configurable.get(
            "max_concurrent_subagents",
            getattr(getattr(app_config, "subagents", None), "max_concurrent", 3),
        )
        pipeline.append(SubagentLimitMiddleware(max_concurrent=max_concurrent))

    # --- Post-processing layer (15-17) ---
    pipeline.append(TitleMiddleware())

    if paper_service:
        pipeline.append(CitationContextMiddleware(paper_service))

    # --- MUST BE LAST (16) ---
    pipeline.append(ClarificationMiddleware())

    return pipeline


async def middleware_before_model(
    state: ThreadState,
    config: RunnableConfig,
    middlewares: list,
) -> ThreadState:
    """Execute all middlewares before model call.

    Args:
        state: Current state
        config: Runtime config
        middlewares: List of middlewares

    Returns:
        Updated state
    """
    current_state = state
    for middleware in middlewares:
        updates = await middleware.before_model(current_state, config)
        if isinstance(updates, dict):
            # Merge updates into state (ThreadState is dict-like)
            current_state = ThreadState(**{**current_state, **updates})
    return current_state


async def middleware_after_model(
    state: ThreadState,
    config: RunnableConfig,
    middlewares: list,
) -> ThreadState:
    """Execute all middlewares after model call.

    Args:
        state: Current state
        config: Runtime config
        middlewares: List of middlewares

    Returns:
        Updated state
    """
    current_state = state
    for middleware in middlewares:
        updates = await middleware.after_model(current_state, config)
        if isinstance(updates, dict):
            current_state = ThreadState(**{**current_state, **updates})
    return current_state


def make_lead_agent(
    config: RunnableConfig,
    middlewares: list | None = None,
    *,
    workspace_service=None,
    index_service=None,
    artifact_service=None,
    paper_service=None,
    sandbox_provider=None,
    memory_queue=None,
) -> Callable:
    """Factory function to create the lead agent.

    This is the entry point registered in langgraph.json.

    Args:
        config: Runtime configuration
        middlewares: Optional list of middleware instances. If not provided,
                    default pipeline will be built using build_pipeline().

    Returns:
        Compiled agent graph
    """
    # Get configuration
    config = _normalize_runtime_config(config)
    configurable = config.get("configurable", {})
    model_name = configurable["model_name"]
    thinking_enabled = configurable.get("thinking_enabled", False)
    reasoning_effort = configurable.get("reasoning_effort")
    subagent_enabled = configurable.get("subagent_enabled", True)

    from src.models.factory import create_chat_model
    base_model = create_chat_model(
        model_name,
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
    )

    # Use provided middlewares or build pipeline
    if middlewares is None:
        middlewares = build_pipeline(
            config,
            workspace_service=workspace_service,
            index_service=index_service,
            artifact_service=artifact_service,
            paper_service=paper_service,
            sandbox_provider=sandbox_provider,
            memory_queue=memory_queue,
        )

    include_execution_tools = any(
        isinstance(middleware, ExecutionMiddleware)
        for middleware in (middlewares or [])
    )

    def _load_tools() -> list[BaseTool]:
        return get_available_tools(
            include_execution=include_execution_tools,
            subagent_enabled=subagent_enabled,
            model_name=model_name,
        )

    tool_node = DynamicToolNode(_load_tools, middlewares=middlewares)

    def _resolve_model(_state, _runtime):
        current_tools = tool_node.list_available_tools()
        if not current_tools:
            return base_model
        return base_model.bind_tools(current_tools)

    # Build system prompt for the agent
    def prompt_fn(state):
        """Generate system prompt from state and config."""
        return apply_prompt_template(ThreadState(**state), config)

    # Create react agent
    agent = create_react_agent(
        _resolve_model,
        tool_node,
        prompt=prompt_fn,
        checkpointer=MemorySaver(),
    )

    return _MiddlewareWrappedAgent(
        agent,
        middlewares=middlewares,
        default_config=config,
    )


class _MiddlewareWrappedAgent:
    """Attach the repo's middleware chain around the LangGraph agent."""

    def __init__(
        self,
        agent: Any,
        *,
        middlewares: list | None,
        default_config: RunnableConfig,
    ) -> None:
        self._agent = agent
        self._middlewares = middlewares or []
        self._default_config = default_config

    async def ainvoke(self, input: dict[str, Any], config: RunnableConfig | None = None, **kwargs):
        runtime_config = _normalize_runtime_config(
            _merge_runtime_config(self._default_config, config)
        )
        state = ThreadState(**(input or {}))
        if self._middlewares:
            state = await middleware_before_model(state, runtime_config, self._middlewares)
        result = await self._agent.ainvoke(state, config=runtime_config, **kwargs)
        return await self._apply_after_model(result, runtime_config)

    def invoke(self, input: dict[str, Any], config: RunnableConfig | None = None, **kwargs):
        runtime_config = _normalize_runtime_config(
            _merge_runtime_config(self._default_config, config)
        )
        state = ThreadState(**(input or {}))
        if self._middlewares:
            state = asyncio.run(
                middleware_before_model(state, runtime_config, self._middlewares)
            )
        result = self._agent.invoke(state, config=runtime_config, **kwargs)
        if not self._middlewares or not isinstance(result, dict):
            return result
        return asyncio.run(
            self._apply_after_model(result, runtime_config)
        )

    async def _apply_after_model(
        self,
        result: Any,
        runtime_config: RunnableConfig,
    ) -> Any:
        if not self._middlewares or not isinstance(result, dict):
            return result
        state = ThreadState(**result)
        return await middleware_after_model(state, runtime_config, self._middlewares)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)
