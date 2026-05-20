"""TaskReport contract — structured output from a capability execution."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Output data payloads
# ---------------------------------------------------------------------------


class LibraryItemData(BaseModel):
    """Data for a library item (paper, book, etc.)."""

    title: str
    authors: list[str]
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    metadata: dict | None = None


class DocumentData(BaseModel):
    """Data for a stored or agent-generated document.

    Two flavours are supported:

    * **File-backed** — caller provides ``storage_path`` (and ideally
      ``mime_type`` and ``size_bytes``).  This is the upload / artefact case.
    * **Inline** — caller provides ``content`` (e.g. an agent-produced
      markdown report).  ``mime_type`` defaults to ``text/markdown`` and the
      commit service materialises the content to managed workspace storage
      before writing the DB row.

    Either ``storage_path`` or ``content`` must be present at commit time.
    """

    name: str
    doc_kind: str = "generic"
    content: str | None = None
    mime_type: str = "text/markdown"
    storage_path: str | None = None
    size_bytes: int = 0
    parent_id: str | None = None


class MemoryFactData(BaseModel):
    """Data for a memory fact to persist."""

    content: str
    category: str = "general"
    confidence: float = 1.0


class DecisionData(BaseModel):
    """Data for a recorded decision."""

    key: str
    value: str
    confidence: float = 1.0


class TaskData(BaseModel):
    """Data for a follow-up task."""

    title: str
    description: str | None = None
    priority: int = 0


# ---------------------------------------------------------------------------
# Discriminated union outputs
# ---------------------------------------------------------------------------


class ResultOutputBase(BaseModel):
    """Common fields for all result outputs."""

    id: str
    preview: str
    default_checked: bool = True


class LibraryItemOutput(ResultOutputBase):
    """A library item result (paper, book, etc.)."""

    kind: Literal["library_item"]
    data: LibraryItemData


class DocumentOutput(ResultOutputBase):
    """A document result."""

    kind: Literal["document"]
    data: DocumentData


class MemoryFactOutput(ResultOutputBase):
    """A memory fact result."""

    kind: Literal["memory_fact"]
    data: MemoryFactData


class DecisionOutput(ResultOutputBase):
    """A decision result."""

    kind: Literal["decision"]
    data: DecisionData


class TaskOutput(ResultOutputBase):
    """A follow-up task result."""

    kind: Literal["task"]
    data: TaskData


ResultOutput = Annotated[
    LibraryItemOutput | DocumentOutput | MemoryFactOutput | DecisionOutput | TaskOutput,
    Field(discriminator="kind"),
]

# ---------------------------------------------------------------------------
# Error record
# ---------------------------------------------------------------------------


class ResultError(BaseModel):
    """Records an error that occurred during execution."""

    phase: str
    task: str
    error: str


# ---------------------------------------------------------------------------
# TaskReport
# ---------------------------------------------------------------------------


class TaskReport(BaseModel):
    """Structured report produced by a capability executor upon completion.

    Attributes:
        execution_id: Unique identifier for this execution run.
        capability_id: Identifier of the capability that was executed.
        status: Outcome status of the execution.
        duration_seconds: Wall-clock duration in seconds.
        token_usage: Optional breakdown of token usage (input/output/total).
        cost_estimate: Optional human-readable cost estimate string.
        narrative: Human-readable summary of what was done.
        outputs: List of result outputs (discriminated by kind).
        errors: List of errors encountered during execution.
    """

    execution_id: str
    capability_id: str
    status: Literal["completed", "failed_partial", "cancelled"]
    duration_seconds: int
    token_usage: dict[str, int] | None = None
    cost_estimate: str | None = None
    narrative: str
    outputs: list[ResultOutput] = Field(default_factory=list)
    errors: list[ResultError] = Field(default_factory=list)
