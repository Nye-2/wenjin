"""Structured chat-block protocol (spec §5.1).

The agent's only output contract: a list of AgentBlock variants.
LangChain `with_structured_output` enforces this schema.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    kind: Literal["text"] = "text"
    content: str


class StatusLineBlock(BaseModel):
    kind: Literal["status_line"] = "status_line"
    label: str
    run_id: str
    phase_index: int | None = None
    tone: Literal["info", "warn", "error"] = "info"


class Pill(BaseModel):
    label: str
    intent: str  # directive sent back to agent on click


class QuestionCardBlock(BaseModel):
    kind: Literal["question_card"] = "question_card"
    label: str
    question: str
    pills: list[Pill] = Field(default_factory=list, max_length=3)
    context_ref_subagent_task_id: str | None = None
    context_ref_phase_index: int | None = None


class Finding(BaseModel):
    id: str  # used by users to reference: "深入第 ① 点"
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
    feedback: FeedbackBlock
    stats: RunStats


AgentBlock = Annotated[
    TextBlock | StatusLineBlock | QuestionCardBlock | ResultCardBlock,
    Field(discriminator="kind"),
]


class AgentMessage(BaseModel):
    blocks: list[AgentBlock]

    def model_dump(self, **kwargs):
        """Override to exclude None values by default."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)
