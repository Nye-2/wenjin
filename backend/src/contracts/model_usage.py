"""Canonical model-usage contracts for durable Mission accounting."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _non_negative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


class ModelUsage(BaseModel):
    """Provider token counters with detail counters treated as subsets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def normalize_total(self) -> ModelUsage:
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens must be a subset of input_tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("reasoning_tokens must be a subset of output_tokens")
        minimum_total = self.input_tokens + self.output_tokens
        if self.total_tokens < minimum_total:
            object.__setattr__(self, "total_tokens", minimum_total)
        return self

    @classmethod
    def from_provider_metadata(cls, raw: Any) -> ModelUsage | None:
        if not isinstance(raw, dict):
            return None
        input_details = raw.get("input_token_details")
        output_details = raw.get("output_token_details")
        usage = cls(
            input_tokens=_non_negative_int(
                raw.get("input_tokens", raw.get("prompt_tokens", raw.get("input", 0)))
            ),
            cached_input_tokens=_non_negative_int(
                input_details.get("cache_read", input_details.get("cached_tokens", 0))
                if isinstance(input_details, dict)
                else raw.get("cached_input_tokens", raw.get("cached_tokens", 0))
            ),
            output_tokens=_non_negative_int(
                raw.get(
                    "output_tokens",
                    raw.get("completion_tokens", raw.get("output", 0)),
                )
            ),
            reasoning_tokens=_non_negative_int(
                output_details.get("reasoning", output_details.get("reasoning_tokens", 0))
                if isinstance(output_details, dict)
                else raw.get("reasoning_tokens", 0)
            ),
            total_tokens=_non_negative_int(raw.get("total_tokens", raw.get("total", 0))),
        )
        return usage if usage.total_tokens > 0 else None


class ModelUsageReceipt(BaseModel):
    """Measured usage for exactly one successful provider response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1, max_length=160)
    usage: ModelUsage
    provider_response_id: str | None = Field(default=None, max_length=512)


class ModelCallLedgerBinding(BaseModel):
    """Semantic identity shared by one started call and its usage receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_call_id: str = Field(min_length=1, max_length=160)
    model_id: str = Field(min_length=1, max_length=160)
    turn: int = Field(ge=1)
    attempt: int = Field(ge=1)
    parent_operation_id: str | None = Field(default=None, max_length=160)
    job_id: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_subagent_binding(self) -> ModelCallLedgerBinding:
        if (self.parent_operation_id is None) != (self.job_id is None):
            raise ValueError(
                "parent_operation_id and job_id must be provided together"
            )
        return self


class ModelCallStartedPayload(ModelCallLedgerBinding):
    """Complete durable payload for one provider dispatch boundary."""


class ModelUsageReceiptPayload(ModelCallLedgerBinding):
    """Complete durable payload for one measured provider response."""

    usage: ModelUsage
    provider_response_id: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def require_non_zero_usage(self) -> ModelUsageReceiptPayload:
        if self.usage.total_tokens <= 0:
            raise ValueError("usage receipt must contain non-zero total_tokens")
        return self


class ModelCallTerminalOutcome(StrEnum):
    """Auditable non-receipt outcomes for one started provider call."""

    FAILED = "failed"
    CANCELLED = "cancelled"
    UNRESOLVED = "unresolved"


class ModelCallTerminalPayload(ModelCallLedgerBinding):
    """Durable terminal fact when a measured usage receipt is unavailable."""

    outcome: ModelCallTerminalOutcome
    error_type: str | None = Field(default=None, max_length=160)
    detail: str = Field(min_length=1, max_length=1000)
    provider_response_id: str | None = Field(default=None, max_length=512)


class ModelCallState(StrEnum):
    """DataService projection of one immutable model-call ledger pair."""

    OPEN = "open"
    RECEIPT = "receipt"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNRESOLVED = "unresolved"


__all__ = [
    "ModelCallLedgerBinding",
    "ModelCallState",
    "ModelCallStartedPayload",
    "ModelCallTerminalOutcome",
    "ModelCallTerminalPayload",
    "ModelUsage",
    "ModelUsageReceipt",
    "ModelUsageReceiptPayload",
]
