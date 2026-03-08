"""ThreadState with academic extensions."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, PrivateAttr


class AcademicArtifact(BaseModel):
    """Academic artifact produced by skills."""
    id: str
    workspace_id: str
    type: str  # research_idea, methodology, framework_outline, abstract, paper_draft
    content: dict
    created_by_skill: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def merge_artifacts(
    existing: list[AcademicArtifact],
    new: list[AcademicArtifact],
) -> list[AcademicArtifact]:
    """Merge artifacts, deduplicating by ID (new takes precedence)."""
    artifact_map = {a.id: a for a in existing}
    artifact_map.update({a.id: a for a in new})
    return list(artifact_map.values())


def merge_dicts(left: dict, right: dict) -> dict:
    """Merge two dictionaries (right takes precedence)."""
    result = left.copy()
    result.update(right)
    return result


def add_messages(left: list, right: list) -> list:
    """Merge messages by appending right to left."""
    return left + right


class ThreadState(BaseModel):
    """Extended ThreadState with academic fields.

    Compatible with LangGraph's AgentState but as a Pydantic model for
    validation and additional academic fields.

    Attributes:
        messages: Conversation messages (LangGraph compatible)
        workspace_id: Current workspace context
        workspace_type: Type of workspace (sci, thesis, proposal, grant)
        artifacts: Academic artifacts produced by skills
        cited_papers: List of paper IDs cited in this thread
        discipline: Academic discipline
    """

    # Core messages (LangGraph compatible)
    messages: Annotated[Sequence[BaseMessage], add_messages] = Field(default_factory=list)

    # Academic context
    workspace_id: str | None = None
    workspace_type: str | None = None  # sci, thesis, proposal, grant

    # Academic artifacts (with deduplication)
    artifacts: Annotated[list[AcademicArtifact], merge_artifacts] = Field(default_factory=list)

    # Literature citation tracking
    cited_papers: list[str] = Field(default_factory=list)

    # Discipline information
    discipline: str | None = None

    # Thread metadata
    thread_data: dict = Field(default_factory=dict)
    title: str | None = None

    # File tracking
    uploaded_files: list[dict] = Field(default_factory=list)
    artifacts_paths: list[str] = Field(default_factory=list)

    # Subagent tracking
    subagent_tasks: dict = Field(default_factory=dict)

    # Internal context (not persisted)
    model_config = {"extra": "allow"}

    # Private context fields (using PrivateAttr for internal state)
    _workspace_config: dict = PrivateAttr(default_factory=dict)
    _literature_context: str = PrivateAttr(default="")
    _knowledge_context: str = PrivateAttr(default="")
    _discipline_norms: dict = PrivateAttr(default_factory=dict)

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get internal context value."""
        return getattr(self, f"_{key}", default)

    def set_context(self, key: str, value: Any) -> None:
        """Set internal context value."""
        setattr(self, f"_{key}", value)
