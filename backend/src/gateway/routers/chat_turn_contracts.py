"""ChatTurnRun transport request/response contracts."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from src.application.results import ThreadTurnAttachment, ThreadTurnRequest
from src.contracts.reasoning import ReasoningEffort
from src.runtime.chat_turns import ChatTurnRunRecord
from src.runtime.chat_turns.schemas import chat_turn_idempotency_key

ChatTurnUploadKind = Literal["literature", "workspace_context", "transient"]


class ChatTurnAttachment(BaseModel):
    """Chat-turn attachment metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: str
    kind: ChatTurnUploadKind = "transient"
    url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    reference_id: str | None = None
    artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatTurnCreateRequest(BaseModel):
    """Create one short-lived transport for a thread turn."""

    model_config = ConfigDict(extra="forbid")

    request_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
    ]
    message: str
    workspace_id: str | None = None
    thread_id: str | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    attachments: list[ChatTurnAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    on_disconnect: Literal["cancel", "continue"] = "cancel"
    multitask_strategy: Literal["reject", "interrupt", "rollback"] = "reject"

    @field_validator("metadata")
    @classmethod
    def _reject_reserved_metadata(
        cls,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if value is None:
            return None
        reserved = sorted(str(key) for key in value if str(key).startswith("_"))
        if reserved:
            raise ValueError("metadata keys beginning with '_' are server-owned")
        return value


class ChatTurnResponse(BaseModel):
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


class ChatTurnWaitResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str
    error: str | None = None
    values: dict[str, Any] | None = None


def to_turn_request(
    body: ChatTurnCreateRequest,
    *,
    actor_id: str,
    forced_thread_id: str | None = None,
) -> ThreadTurnRequest:
    thread_id = forced_thread_id if forced_thread_id is not None else body.thread_id
    if not thread_id or not thread_id.strip():
        raise ValueError("thread-bound chat turn requires thread_id")
    return ThreadTurnRequest(
        message=body.message,
        workspace_id=body.workspace_id,
        thread_id=thread_id,
        model=body.model,
        reasoning_effort=body.reasoning_effort,
        attachments=tuple(ThreadTurnAttachment(**item.model_dump()) for item in body.attachments),
        metadata=dict(body.metadata or {}) or None,
        turn_idempotency_key=chat_turn_idempotency_key(
            body.request_id,
            actor_id=actor_id,
        ),
    )


def record_to_response(record: ChatTurnRunRecord) -> ChatTurnResponse:
    public_metadata = {str(key): value for key, value in dict(record.metadata).items() if not str(key).startswith("_")}
    return ChatTurnResponse(
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
