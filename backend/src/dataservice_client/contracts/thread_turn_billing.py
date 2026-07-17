"""Typed DataService contracts for atomic chat-turn billing."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.contracts.billing import ThreadTurnBillingStatus
from src.contracts.model_usage import ModelUsage
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagePayload,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ThreadTurnBillingPayload(_StrictModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    thread_id: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    idempotency_key: str
    model_id: str
    status: ThreadTurnBillingStatus
    reserved_credits: int = Field(ge=0)
    reserved_free_tokens: int = Field(ge=0)
    settled_credits: int = Field(ge=0)
    token_usage: ModelUsage
    pricing_snapshot: dict[str, Any]
    transaction_id: str | None = None
    expires_at: datetime
    settled_at: datetime | None = None
    released_at: datetime | None = None
    release_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_financial_state(self) -> ThreadTurnBillingPayload:
        if self.settled_credits > self.reserved_credits:
            raise ValueError("settled credits exceed the authorized hold")
        usage_total = self.token_usage.total_tokens
        if self.status == ThreadTurnBillingStatus.AUTHORIZED:
            valid = (
                self.settled_at is None
                and self.released_at is None
                and self.transaction_id is None
                and usage_total == 0
            )
        elif self.status == ThreadTurnBillingStatus.SETTLED:
            valid = (
                self.settled_at is not None
                and self.released_at is None
                and self.transaction_id is not None
                and usage_total > 0
            )
        else:
            valid = (
                self.settled_at is None
                and self.released_at is not None
                and self.transaction_id is None
                and usage_total == 0
            )
        if not valid:
            raise ValueError("chat-turn billing state is internally inconsistent")
        return self


class ThreadTurnAuthorizePayload(_StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=200)
    model_id: str = Field(min_length=1, max_length=120)
    user_message: ConversationMessageCreatePayload

    @model_validator(mode="after")
    def validate_user_message(self) -> ThreadTurnAuthorizePayload:
        if self.user_message.role != "user":
            raise ValueError("thread-turn authorization requires a user message")
        return self


class ThreadTurnAuthorizationResultPayload(_StrictModel):
    billing: ThreadTurnBillingPayload
    user_message: ConversationMessagePayload | None = None
    assistant_message: ConversationMessagePayload | None = None
    created: bool


class ThreadTurnCompletePayload(_StrictModel):
    user_id: str = Field(min_length=1, max_length=36)
    assistant_message: ConversationMessageCreatePayload
    token_usage: ModelUsage

    @model_validator(mode="after")
    def validate_assistant_message(self) -> ThreadTurnCompletePayload:
        if self.assistant_message.role != "assistant":
            raise ValueError("thread-turn completion requires an assistant message")
        return self


class ThreadTurnCompletionResultPayload(_StrictModel):
    billing: ThreadTurnBillingPayload
    assistant_message: ConversationMessagePayload
    billing_metadata: dict[str, Any] = Field(default_factory=dict)


class ThreadTurnReleasePayload(_StrictModel):
    user_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=1, max_length=1000)


class ThreadTurnReleaseByKeyPayload(ThreadTurnReleasePayload):
    idempotency_key: str = Field(min_length=1, max_length=200)


class ThreadTurnReleaseByKeyResultPayload(_StrictModel):
    billing: ThreadTurnBillingPayload | None = None


class ThreadTurnRollbackPayload(_StrictModel):
    user_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=1, max_length=1000)


class ThreadTurnRollbackResultPayload(_StrictModel):
    billing: ThreadTurnBillingPayload
    message_rolled_back: bool


class ThreadTurnReconcilePayload(_StrictModel):
    now: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class ThreadTurnReconcileResultPayload(_StrictModel):
    expired_billing_ids: list[str] = Field(default_factory=list)


__all__ = [
    "ThreadTurnAuthorizationResultPayload",
    "ThreadTurnAuthorizePayload",
    "ThreadTurnBillingPayload",
    "ThreadTurnCompletePayload",
    "ThreadTurnCompletionResultPayload",
    "ThreadTurnReconcilePayload",
    "ThreadTurnReconcileResultPayload",
    "ThreadTurnReleaseByKeyPayload",
    "ThreadTurnReleaseByKeyResultPayload",
    "ThreadTurnReleasePayload",
    "ThreadTurnRollbackPayload",
    "ThreadTurnRollbackResultPayload",
]
