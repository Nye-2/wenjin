"""ThreadState with academic extensions.

Extends deer-flow's AgentState (TypedDict-based) with academic-specific fields
for workspace context, literature tracking, and artifact management.

AgentState is defined locally to match deer-flow's pattern (TypedDict with
add_messages reducer on messages) while avoiding a broken import chain in
langchain 1.2.x (langchain.agents.__init__ -> langchain.schema ->
langchain_core.memory which was removed in langchain_core >= 1.2).
"""

from datetime import UTC, datetime
from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


# ============ AgentState base (deer-flow compatible) ============


class AgentState(TypedDict):
    """Base agent state compatible with deer-flow's AgentState.

    Provides the messages field with the add_messages reducer,
    which is the core requirement for LangGraph agent workflows.
    """
    messages: Annotated[list[AnyMessage], add_messages]


# ============ Supporting Types ============


class SandboxState(TypedDict):
    """Sandbox execution state."""
    sandbox_id: NotRequired[str | None]


class ThreadDataState(TypedDict):
    """Per-thread directory paths."""
    workspace_path: NotRequired[str | None]
    uploads_path: NotRequired[str | None]
    outputs_path: NotRequired[str | None]


class ViewedImageData(TypedDict):
    """Image data for vision support."""
    base64: str
    mime_type: str


# ============ Pydantic Models (still needed for structured data) ============


class AcademicArtifact(BaseModel):
    """Academic artifact produced by skills."""
    id: str
    workspace_id: str
    type: str  # research_idea, methodology, framework_outline, abstract, paper_draft
    content: dict
    created_by_skill: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ============ Reducers ============


def merge_artifacts(
    existing: list[str] | None,
    new: list[str] | None,
) -> list[str]:
    """Reducer for artifacts list (string paths, deer-flow style) - merges and deduplicates."""
    if existing is None:
        return new or []
    if new is None:
        return existing
    # Use dict.fromkeys to deduplicate while preserving order
    return list(dict.fromkeys(existing + new))


def merge_response_blocks(
    existing: list[dict[str, Any]] | None,
    new: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Reducer for structured response blocks emitted during a chat turn."""
    if existing is None:
        return [block for block in (new or []) if isinstance(block, dict)]
    if new is None:
        return existing
    return [
        *existing,
        *(block for block in new if isinstance(block, dict)),
    ]


def merge_response_metadata(
    existing: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> dict[str, Any]:
    """Reducer for structured response metadata emitted during a chat turn."""
    if existing is None:
        return dict(new or {})
    if new is None:
        return existing

    merged = dict(existing)
    for key, value in new.items():
        if (
            key == "artifacts"
            and isinstance(merged.get(key), list)
            and isinstance(value, list)
        ):
            deduped: list[Any] = []
            seen: set[str] = set()
            for item in [*merged[key], *value]:
                marker = repr(item)
                if marker in seen:
                    continue
                seen.add(marker)
                deduped.append(item)
            merged[key] = deduped
            continue
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
            continue
        merged[key] = value
    return merged


def merge_academic_artifacts(
    existing: list[AcademicArtifact] | None,
    new: list[AcademicArtifact] | None,
) -> list[AcademicArtifact]:
    """Reducer for academic artifacts - merges and deduplicates by ID (new takes precedence)."""
    if existing is None:
        return new or []
    if new is None:
        return existing
    artifact_map = {a.id: a for a in existing}
    artifact_map.update({a.id: a for a in new})
    return list(artifact_map.values())


def merge_cited_papers(
    existing: list[str] | None,
    new: list[str] | None,
) -> list[str]:
    """Reducer for cited papers - merges and deduplicates."""
    if existing is None:
        return new or []
    if new is None:
        return existing
    return list(dict.fromkeys(existing + new))


def merge_viewed_images(
    existing: dict[str, ViewedImageData] | None,
    new: dict[str, ViewedImageData] | None,
) -> dict[str, ViewedImageData]:
    """Reducer for viewed_images dict - merges image dictionaries.

    Special case: If new is an empty dict {}, it clears the existing images.
    This allows middlewares to clear the viewed_images state after processing.
    """
    if existing is None:
        return new or {}
    if new is None:
        return existing
    # Special case: empty dict means clear all viewed images
    if len(new) == 0:
        return {}
    # Merge dictionaries, new values override existing ones for same keys
    return {**existing, **new}


# ============ ThreadState ============


class ThreadState(AgentState):
    """Extended ThreadState with deer-flow base fields and academic extensions.

    Inherits from AgentState (TypedDict-based) which provides:
        - messages: Annotated list with add_messages reducer

    Deer-flow infrastructure fields:
        - sandbox: SandboxState for execution environment
        - thread_data: ThreadDataState for per-thread directories
        - title: Auto-generated thread title
        - artifacts: String paths (deer-flow style, with dedup reducer)
        - todos: Task list for plan mode
        - uploaded_files: List of uploaded file info dicts
        - viewed_images: Image data dict with merge reducer

    Academic-specific fields (NotRequired):
        - workspace_id: Current workspace context
        - workspace_type: Type of workspace (sci, thesis, proposal, software_copyright, patent)
        - discipline: Academic discipline
        - workspace_config: Workspace configuration (was _workspace_config)
        - literature_context: Literature context string (was _literature_context)
        - knowledge_context: Workspace artifact context (was _knowledge_context)
        - memory_context: Long-term user memory context
        - discipline_norms: Discipline-specific norms (was _discipline_norms)
        - current_skill: Currently executing skill name
        - academic_artifacts: AcademicArtifact list with merge reducer
        - cited_papers: Paper ID list with dedup reducer
        - subagent_tasks: Subagent task tracking
    """

    # Deer-flow base fields
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    response_blocks: Annotated[list[dict[str, Any]], merge_response_blocks]
    response_metadata: Annotated[dict[str, Any], merge_response_metadata]
    todos: NotRequired[list | None]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]

    # Academic context fields (formerly private attrs)
    workspace_id: NotRequired[str | None]
    workspace_type: NotRequired[str | None]
    discipline: NotRequired[str | None]
    workspace_config: NotRequired[dict[str, Any] | None]
    literature_context: NotRequired[str | None]
    knowledge_context: NotRequired[str | None]
    memory_context: NotRequired[str | None]
    discipline_norms: NotRequired[dict[str, Any] | None]
    current_skill: NotRequired[str | None]

    # Academic artifacts with deduplication reducer
    academic_artifacts: Annotated[list[AcademicArtifact], merge_academic_artifacts]

    # Citation tracking with deduplication reducer
    cited_papers: Annotated[list[str], merge_cited_papers]

    # Subagent tracking
    subagent_tasks: NotRequired[dict | None]
