"""Lead Agent factory for AcademiaGPT."""

import logging
from collections.abc import Callable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from src.agents.middlewares import (
    CitationContextMiddleware,
    ClarificationMiddleware,
    DanglingToolCallMiddleware,
    DisciplineContextMiddleware,
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
from src.config.config_loader import get_app_config

logger = logging.getLogger(__name__)


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
            "thesis": "Graduate Thesis",
            "proposal": "Research Proposal",
            "grant": "Grant Application",
        }
        base_prompt += f"\n\n## Current Project\nProject Type: {type_labels.get(workspace_type, workspace_type)}"

    if discipline:
        base_prompt += f"\nDiscipline: {discipline.replace('_', ' ').title()}"

    # Add literature context
    literature_context = state.get("literature_context", "")
    if literature_context:
        base_prompt += f"\n\n{literature_context}"

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

    # Add available skills
    base_prompt += "\n\n## Available Skills\nUse these skills for specific academic tasks:\n- deep-research: Comprehensive literature analysis and idea generation\n- framework-designer: Generate paper abstract and outline\n- fullpaper-writer: Complete paper writing\n- literature-review: Generate literature review\n- proposal-writer: Write research proposals\n- experiment-designer: Design experiments\n- peer-reviewer: Review and critique papers\n- journal-recommender: Recommend journals for submission"

    return base_prompt


def get_available_tools(
    groups: list[str] | None = None,
    include_mcp: bool = True,
    model_name: str | None = None,
    subagent_enabled: bool = True,
) -> list[BaseTool]:
    """Get available tools based on configuration.

    Args:
        groups: Tool groups to include (None = all)
        include_mcp: Include MCP tools
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
        ls_tool,
        present_files_tool,
        read_file_tool,
        str_replace_tool,
        write_file_tool,
    )

    # File system tools
    tools.extend([
        bash_tool,
        read_file_tool,
        write_file_tool,
        str_replace_tool,
        ls_tool,
    ])

    # Interaction tools
    tools.append(ask_clarification_tool)

    # Output tools
    tools.append(present_files_tool)

    # Academic tools
    try:
        from src.academic.tools.semantic_scholar import semantic_scholar_search_tool
        tools.append(semantic_scholar_search_tool)
    except ImportError:
        pass  # Academic tools not yet implemented

    # Literature navigation tools (TOC-driven)
    try:
        from src.academic.literature.tools import (
            list_papers,
            get_section,
            search_external,
            get_paper_by_doi,
            # Workspace/paper management tools
            create_workspace,
            get_workspace,
            list_workspaces,
            add_paper_to_workspace,
            remove_paper_from_workspace,
            # External import tool
            import_paper,
        )
        tools.extend([
            list_papers,
            get_section,
            search_external,
            get_paper_by_doi,
            create_workspace,
            get_workspace,
            list_workspaces,
            add_paper_to_workspace,
            remove_paper_from_workspace,
            import_paper,
        ])
    except ImportError:
        pass  # Literature tools not yet implemented

    # Citation management tools
    try:
        from src.academic.citation.tools import (
            format_citation,
            format_bibliography,
            export_bibtex,
            import_bibtex,
            get_citation_graph,
            add_citation,
        )
        tools.extend([
            format_citation,
            format_bibliography,
            export_bibtex,
            import_bibtex,
            get_citation_graph,
            add_citation,
        ])
    except ImportError:
        pass  # Citation tools not yet implemented

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
    """Build the 16-layer middleware pipeline.

    Order:
    1.  ThreadDataMiddleware       - Infrastructure
    2.  UploadsMiddleware          - Infrastructure
    3.  SandboxMiddleware          - Infrastructure (new)
    4.  DanglingToolCallMiddleware - Fix
    5.  SummarizationMiddleware    - Context management (conditional)
    6.  MemoryMiddleware           - Context management (new, conditional)
    7.  WorkspaceContextMiddleware - Academic (conditional)
    8.  LiteratureContextMiddleware - Academic (conditional)
    9.  KnowledgeContextMiddleware - Academic (conditional)
    10. DisciplineContextMiddleware - Academic
    11. TodoListMiddleware         - Interaction (new, conditional)
    12. ViewImageMiddleware        - Interaction (new)
    13. SubagentLimitMiddleware    - Control (conditional)
    14. TitleMiddleware            - Post-processing
    15. CitationContextMiddleware  - Post-processing (conditional)
    16. ClarificationMiddleware    - Control (MUST BE LAST)
    """
    configurable = config.get("configurable", {})
    is_plan_mode = configurable.get("is_plan_mode", False)
    subagent_enabled = configurable.get("subagent_enabled", False)

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

    # Sandbox (3) - requires provider
    if sandbox_provider:
        pipeline.append(SandboxMiddleware(sandbox_provider))

    # --- Fix layer (4) ---
    pipeline.append(DanglingToolCallMiddleware())

    # --- Context management layer (5-6) ---
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
    if memory_config and getattr(memory_config, "enabled", False) and memory_queue:
        pipeline.append(MemoryMiddleware(queue=memory_queue, enabled=True))

    # --- Academic context layer (7-10) ---
    if workspace_service:
        pipeline.append(WorkspaceContextMiddleware(workspace_service))
    if index_service:
        pipeline.append(LiteratureContextMiddleware(index_service))
    if artifact_service:
        pipeline.append(KnowledgeContextMiddleware(artifact_service))
    pipeline.append(DisciplineContextMiddleware())

    # --- Interaction layer (11-13) ---
    # TodoList (11) - plan mode only
    if is_plan_mode:
        pipeline.append(TodoListMiddleware())

    # ViewImage (12) - always present, handles vision internally
    pipeline.append(ViewImageMiddleware())

    # SubagentLimit (13) - subagents enabled
    if subagent_enabled:
        max_concurrent = configurable.get("max_concurrent_subagents", 3)
        pipeline.append(SubagentLimitMiddleware(max_concurrent=max_concurrent))

    # --- Post-processing layer (14-16) ---
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


def make_lead_agent(config: RunnableConfig, middlewares: list | None = None) -> Callable:
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
    configurable = config.get("configurable", {})
    model_name = configurable.get("model_name", "gpt-4o")
    thinking_enabled = configurable.get("thinking_enabled", False)
    subagent_enabled = configurable.get("subagent_enabled", True)

    # Create model
    from src.models.factory import create_chat_model
    model = create_chat_model(model_name, thinking_enabled=thinking_enabled)

    # Get tools
    tools = get_available_tools(
        subagent_enabled=subagent_enabled,
        model_name=model_name,
    )

    # Use provided middlewares or build pipeline
    if middlewares is None:
        middlewares = build_pipeline(config)

    # Create agent with custom state modifier
    def state_modifier(state):
        """Modify state before passing to model."""
        # Apply middlewares synchronously (will be async in actual use)
        return {
            **state,
            "system_prompt": apply_prompt_template(ThreadState(**state), config),
        }

    # Create react agent
    agent = create_react_agent(
        model,
        tools,
        state_modifier=state_modifier,
        checkpointer=MemorySaver(),
    )

    return agent
