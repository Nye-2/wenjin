"""Application-layer result objects."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FeatureTaskSubmission:
    task_id: str
    feature_id: str
    message: str
    reused_existing_task: bool = False

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
