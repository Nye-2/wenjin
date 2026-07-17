"""Canonical model-usage contracts for durable Mission accounting."""

from __future__ import annotations

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


__all__ = ["ModelUsage", "ModelUsageReceipt"]
