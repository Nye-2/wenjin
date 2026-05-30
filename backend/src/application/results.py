"""Application-layer result objects."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FeatureTaskSubmission:
    task_id: str
    feature_id: str
    message: str
    reused_existing_task: bool = False
    execution_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FeatureExecutionAdvisory:
    feature_id: str
    code: str
    message: str
    context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FeatureExecutionOutcome = FeatureTaskSubmission | FeatureExecutionAdvisory


@dataclass(frozen=True, slots=True)
class FeatureLaunchResult:
    execution_id: str
    outcome: FeatureExecutionOutcome


@dataclass(frozen=True, slots=True)
class ThreadTurnAttachment:
    name: str
    path: str
    kind: str = "transient"
    url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    reference_id: str | None = None
    artifact_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ThreadTurnRequest:
    message: str
    workspace_id: str | None = None
    thread_id: str | None = None
    model: str | None = None
    skill: str | None = None
    thinking_enabled: bool = False
    reasoning_effort: str | None = None
    attachments: tuple[ThreadTurnAttachment, ...] = ()
    metadata: dict[str, Any] | None = None
    skill_explicit: bool = False


@dataclass(slots=True)
class GeneratedThreadReply:
    """Internal reply container supporting structured thread cards."""

    content: str
    blocks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PreparedThreadTurn:
    request: ThreadTurnRequest
    thread: Any
    user_message_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompletedThreadTurn:
    thread: Any
    assistant_message: dict[str, Any]
    reply: GeneratedThreadReply


@dataclass(frozen=True, slots=True)
class ThesisStatusResult:
    task_id: str
    status: str
    progress: float
    current_phase: str | None = None
    message: str | None = None
    pdf_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


@dataclass(frozen=True, slots=True)
class ThesisPreviewResult:
    task_id: str
    latex_content: str
    sections_completed: int
    sections_total: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


@dataclass(frozen=True, slots=True)
class ThesisCancelResult:
    task_id: str
    status: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
