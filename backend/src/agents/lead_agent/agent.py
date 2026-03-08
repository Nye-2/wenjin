"""Lead Agent factory for AcademiaGPT."""

from typing import Any, Callable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from src.agents.thread_state import ThreadState
from src.agents.middlewares import (
    WorkspaceContextMiddleware,
    LiteratureContextMiddleware,
    KnowledgeContextMiddleware,
    DisciplineContextMiddleware,
    CitationContextMiddleware,
)
from src.config import settings


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
1. **Literature Search**: Search Semantic Scholar for relevant papers
2. **RAG Retrieval**: Search through papers in the current workspace
3. **Subagent Delegation**: Delegate complex tasks to specialized agents

## Guidelines

- Always cite sources when making claims
- Follow academic writing standards appropriate to the discipline
- Be thorough but concise
- Ask for clarification when needed"""

    # Add workspace context
    workspace_type = state.workspace_type
    discipline = state.discipline

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

    # Add literature context (private field)
    literature_context = state.get_context("literature_context", "")
    if literature_context:
        base_prompt += f"\n\n{literature_context}"

    # Add knowledge context (private field)
    knowledge_context = state.get_context("knowledge_context", "")
    if knowledge_context:
        base_prompt += f"\n\n{knowledge_context}"

    # Add discipline norms (private field)
    discipline_norms = state.get_context("discipline_norms", {})
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
        bash_tool,
        read_file_tool,
        write_file_tool,
        str_replace_tool,
        ls_tool,
        ask_clarification_tool,
        present_files_tool,
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
        from src.academic.literature.rag.tools import rag_retrieve_tool
        from src.academic.tools.semantic_scholar import semantic_scholar_search_tool
        tools.extend([rag_retrieve_tool, semantic_scholar_search_tool])
    except ImportError:
        pass  # Academic tools not yet implemented

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
            # Merge updates into state using model_dump
            current_state = ThreadState(**{**current_state.model_dump(), **updates})
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
            current_state = ThreadState(**{**current_state.model_dump(), **updates})
    return current_state


def make_lead_agent(config: RunnableConfig, middlewares: list | None = None) -> Callable:
    """Factory function to create the lead agent.

    This is the entry point registered in langgraph.json.

    Args:
        config: Runtime configuration
        middlewares: Optional list of middleware instances. If not provided,
                    default middlewares will be built without services.

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

    # Use provided middlewares or build default ones
    if middlewares is None:
        middlewares = build_middlewares()

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
