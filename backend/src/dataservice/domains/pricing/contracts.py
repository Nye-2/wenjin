"""Pricing policy domain contracts and simulation models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GlobalCreditPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credits_per_cny: float = Field(gt=0)
    usd_to_cny: float = Field(default=7.3, gt=0)
    target_margin_floor: float = Field(default=0.9, ge=0)
    show_token_details_to_users: bool = False


class ModelRawCostPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_usd_per_1m: float = Field(default=0.0, ge=0)
    cached_input_usd_per_1m: float = Field(default=0.0, ge=0)
    output_usd_per_1m: float = Field(default=0.0, ge=0)
    reasoning_usd_per_1m: float = Field(default=0.0, ge=0)


class ModelUsagePolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_weight: float = Field(default=0.3, ge=0)
    cached_input_weight: float = Field(default=0.05, ge=0)
    output_weight: float = Field(default=1.0, ge=0)
    reasoning_weight: float = Field(default=1.0, ge=0)
    credits_per_1k_weighted_tokens: float = Field(default=6.0, gt=0)
    min_chat_credits: int = Field(default=3, ge=0)
    min_feature_model_credits: int = Field(default=10, ge=0)
    cost_guard_multiplier: float = Field(default=20.0, ge=1.0)
    raw_cost: ModelRawCostPolicyConfig = Field(default_factory=ModelRawCostPolicyConfig)
    free_tokens: int = Field(default=0, ge=0)
    max_overdraft_credits: int = Field(default=100, ge=0)


class CapabilityPricingPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_type: str | None = None
    capability_id: str | None = None
    base_fee_credits: int = Field(default=0, ge=0)
    estimate_min_credits: int = Field(default=0, ge=0)
    estimate_max_credits: int = Field(ge=0)
    max_charge_credits: int = Field(ge=0)
    included_revision_loops: int = Field(default=0, ge=0)
    platform_failed_refund: str = "full"
    user_cancel_policy: str = "settle_completed_usage"

    @model_validator(mode="after")
    def validate_charge_bounds(self) -> CapabilityPricingPolicyConfig:
        if self.max_charge_credits < self.estimate_max_credits:
            raise ValueError("max_charge_credits must be greater than or equal to estimate_max_credits")
        return self


class ToolPricingPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_key: str
    base_credits: int = Field(ge=0)


class SandboxPricingPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tiers: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_tiers(self) -> SandboxPricingPolicyConfig:
        if not self.tiers:
            raise ValueError("sandbox pricing requires at least one tier")
        return self


class PricingSimulationRequest(BaseModel):
    policy_kind: str
    surface: str = "chat"
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
