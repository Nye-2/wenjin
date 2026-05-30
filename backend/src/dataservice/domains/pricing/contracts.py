"""Pricing policy domain contracts and simulation models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class GlobalCreditPolicyConfig(BaseModel):
    credits_per_cny: float = Field(gt=0)


class ModelUsagePolicyConfig(BaseModel):
    tokens_per_credit: int = Field(default=1000, gt=0)
    prompt_token_weight: float = Field(default=1.0, ge=0)
    completion_token_weight: float = Field(default=4.0, ge=0)
    minimum_credits: int = Field(default=1, ge=0)
    input_cny_per_1k_tokens: float = Field(default=0.0, ge=0)
    output_cny_per_1k_tokens: float = Field(default=0.0, ge=0)
    raw_cost_markup: float = Field(default=1.5, ge=1.0)


class CapabilityPricingPolicyConfig(BaseModel):
    estimate_min_credits: int = Field(default=0, ge=0)
    estimate_max_credits: int = Field(ge=0)
    max_charge_credits: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_charge_bounds(self) -> CapabilityPricingPolicyConfig:
        if self.max_charge_credits < self.estimate_max_credits:
            raise ValueError("max_charge_credits must be greater than or equal to estimate_max_credits")
        return self


class ToolPricingPolicyConfig(BaseModel):
    tool_key: str
    base_credits: int = Field(ge=0)


class SandboxPricingPolicyConfig(BaseModel):
    tiers: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_tiers(self) -> SandboxPricingPolicyConfig:
        if not self.tiers:
            raise ValueError("sandbox pricing requires at least one tier")
        return self


class PricingSimulationRequest(BaseModel):
    policy_kind: str
    global_policy: GlobalCreditPolicyConfig = Field(default_factory=lambda: GlobalCreditPolicyConfig(credits_per_cny=10))
    model_usage_policy: ModelUsagePolicyConfig | None = None
    capability_policy: CapabilityPricingPolicyConfig | None = None
    tool_policy: ToolPricingPolicyConfig | None = None
    sandbox_policy: SandboxPricingPolicyConfig | None = None
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


class PricingSimulationResult(BaseModel):
    charge_credits: int
    raw_cost_cny: float = 0
    margin_cny: float = 0
    breakdown: dict[str, Any] = Field(default_factory=dict)


class PricingPolicyRecord(BaseModel):
    id: str | None = None
    policy_key: str
    policy_kind: str
    name: str
    enabled: bool = True
    version: int = 1
    config: dict[str, Any] = Field(default_factory=dict)
    created_by_admin_id: str | None = None
    updated_by_admin_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PricingPolicyCreateCommand(BaseModel):
    policy_key: str
    policy_kind: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class PricingPolicyUpdateCommand(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
