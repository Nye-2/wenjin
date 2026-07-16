"""Persisted presentation blocks emitted by WorkspaceAgent and mission projections."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    kind: Literal["text"] = "text"
    content: str


class ThinkingBlock(BaseModel):
    kind: Literal["thinking"] = "thinking"
    text: str


class StatusLineBlock(BaseModel):
    kind: Literal["status_line"] = "status_line"
    label: str
    run_id: str
    phase_index: int | None = None
    tone: Literal["info", "warn", "error"] = "info"
    action: Literal[
        "start_mission",
        "steer_mission",
        "propose_review",
        "request_commit",
    ] | None = None


class Pill(BaseModel):
    label: str
    intent: str


class QuestionCardBlock(BaseModel):
    kind: Literal["question_card"] = "question_card"
    label: str
    question: str
    pills: list[Pill] = Field(default_factory=list, max_length=3)


class Finding(BaseModel):
    id: str
    text: str


class Recommend(BaseModel):
    label: str
    body: str


class Link(BaseModel):
    icon: str
    label: str
    href: str


class FeedbackPill(BaseModel):
    kind: Literal["primary", "normal", "warn"]
    label: str
    intent: str


class FeedbackBlock(BaseModel):
    question: str
    pills: list[FeedbackPill]
    allow_free_input: bool = True


class RunStats(BaseModel):
    duration_ms: int
    subagents: int
    tokens: int


class ResultCardBlock(BaseModel):
    kind: Literal["result_card"] = "result_card"
    run_id: str
    title: str
    tldr: str
    full_summary: str | None = None
    findings: list[Finding]
    recommend: Recommend | None = None
    links: list[Link] = Field(default_factory=list)
    review_items: list[dict[str, Any]] = Field(default_factory=list)
    feedback: FeedbackBlock
    stats: RunStats


AgentBlock = Annotated[
    TextBlock | ThinkingBlock | StatusLineBlock | QuestionCardBlock | ResultCardBlock,
    Field(discriminator="kind"),
]


class AgentMessage(BaseModel):
    blocks: list[AgentBlock]

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)
