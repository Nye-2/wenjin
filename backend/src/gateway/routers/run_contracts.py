"""Shared request/response contracts for run lifecycle routers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.application.results import ThreadTurnAttachment, ThreadTurnRequest
from src.runtime.runs import RunRecord

ReasoningEffort = Literal["minimal", "low", "medium", "high"]
RunUploadKind = Literal["literature", "workspace_context", "transient"]


class RunAttachment(BaseModel):
    """Run-scoped attachment metadata."""

    name: str
    path: str
    kind: RunUploadKind = "transient"
    url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    paper_id: str | None = None
    artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunCreateRequest(BaseModel):
    """Create a run for one thread turn."""

    message: str
    workspace_id: str | None = None
    thread_id: str | None = None
    model: str | None = None
    skill: str | None = None
    thinking_enabled: bool = False
    reasoning_effort: ReasoningEffort | None = None
    attachments: list[RunAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    on_disconnect: Literal["cancel", "continue"] = "cancel"
    multitask_strategy: Literal["reject", "interrupt", "rollback"] = "reject"


class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    assistant_id: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    multitask_strategy: str = "reject"
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""


class RunWaitResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str
    error: str | None = None
    values: dict[str, Any] | None = None


def to_turn_request(
    body: RunCreateRequest,
    *,
    forced_thread_id: str | None = None,
) -> ThreadTurnRequest:
    return ThreadTurnRequest(
        message=body.message,
        workspace_id=body.workspace_id,
        thread_id=forced_thread_id if forced_thread_id is not None else body.thread_id,
        model=body.model,
        skill=body.skill,
        thinking_enabled=body.thinking_enabled,
        reasoning_effort=body.reasoning_effort,
        attachments=tuple(ThreadTurnAttachment(**item.model_dump()) for item in body.attachments),
        metadata=body.metadata,
        skill_explicit="skill" in body.model_fields_set,
    )


def record_to_response(record: RunRecord) -> RunResponse:
    public_metadata = {
        str(key): value
        for key, value in dict(record.metadata).items()
        if not str(key).startswith("_")
    }
    return RunResponse(
        run_id=record.run_id,
        thread_id=record.thread_id,
        assistant_id=record.assistant_id,
        status=record.status.value,
        metadata=public_metadata,
        kwargs=record.kwargs,
        multitask_strategy=record.multitask_strategy,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
