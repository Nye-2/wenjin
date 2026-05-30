"""Pricing policy contracts returned by DataService client methods."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PricingSimulationRequestPayload(BaseModel):
    policy_kind: str
    global_policy: dict[str, Any] = Field(default_factory=lambda: {"credits_per_cny": 10})
    model_usage_policy: dict[str, Any] | None = None
    capability_policy: dict[str, Any] | None = None
    tool_policy: dict[str, Any] | None = None
    sandbox_policy: dict[str, Any] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
