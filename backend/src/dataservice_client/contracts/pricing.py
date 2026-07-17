"""Pricing policy contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PricingPolicyPayload(BaseModel):
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


class ResolvedModelUsagePricingPayload(BaseModel):
    model_id: str
    model_policy: PricingPolicyPayload
    global_policy: PricingPolicyPayload | None = None


class PricingPolicyCreatePayload(BaseModel):
    policy_key: str
    policy_kind: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    admin_id: str | None = None


class PricingPolicyUpdatePayload(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    admin_id: str | None = None


class PricingSimulationRequestPayload(BaseModel):
    policy_kind: str
    surface: str = "chat"
    global_policy: dict[str, Any] = Field(default_factory=lambda: {"credits_per_cny": 10})
    model_usage_policy: dict[str, Any] | None = None
    mission_policy: dict[str, Any] | None = None
    tool_policy: dict[str, Any] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


class PublicModelPricingPayload(BaseModel):
    model_id: str
    display_name: str
    is_default: bool
    policy_id: str
    policy_key: str
    policy_version: int
    minimum_credits: int


class PublicMissionPricingPayload(BaseModel):
    policy_id: str
    policy_key: str
    policy_version: int
    workspace_type: str | None = None
    mission_policy_id: str | None = None
    base_fee_credits: int
    estimate_min_credits: int
    estimate_max_credits: int
    max_charge_credits: int


class PublicPricingCatalogPayload(BaseModel):
    unit: str = "credits"
    chat_models: list[PublicModelPricingPayload] = Field(default_factory=list)
    missions: list[PublicMissionPricingPayload] = Field(default_factory=list)
