"""Model catalog contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.models.capability_profile import (
    GenerationAPI,
    ModelCapabilityProbeEvidence,
    ModelCapabilityProfile,
)


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelCatalogPayload(_StrictContract):
    id: str | None = None
    model_id: str
    display_name: str
    generation_api: GenerationAPI | None
    provider_name: str = "Custom"
    category: str = "llm"
    model_name: str
    base_url: str
    api_key_redacted: str | None = None
    enabled: bool = True
    is_default: bool = False
    capability_profile: ModelCapabilityProfile
    capability_probe: ModelCapabilityProbeEvidence
    capability_probe_hash: str
    capability_observed_at: datetime
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: float | None = None
    max_retries: int | None = None
    trust_level: str = "custom"
    pricing_policy_id: str | None = None
    config_version: int = 1
    health_status: str = "unknown"
    last_tested_at: datetime | None = None
    last_test_error: str | None = None
    default_headers: dict[str, Any] = Field(default_factory=dict)
    created_by_admin_id: str | None = None
    updated_by_admin_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelRuntimeConfigPayload(_StrictContract):
    model_id: str
    display_name: str
    generation_api: GenerationAPI | None
    provider_name: str = "Custom"
    category: str = "llm"
    model_name: str
    base_url: str
    api_key: str
    is_default: bool = False
    capability_profile: ModelCapabilityProfile
    capability_probe: ModelCapabilityProbeEvidence
    capability_probe_hash: str
    capability_observed_at: datetime
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: float | None = None
    max_retries: int | None = None
    trust_level: str = "custom"
    pricing_policy_id: str | None = None
    config_version: int = 1
    default_headers: dict[str, Any] = Field(default_factory=dict)


class ModelCatalogCreatePayload(_StrictContract):
    model_id: str
    display_name: str
    generation_api: GenerationAPI | None = None
    provider_name: str = "Custom"
    category: str = "llm"
    model_name: str
    base_url: str
    api_key: str
    enabled: bool = True
    is_default: bool = False
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: float | None = None
    max_retries: int | None = None
    trust_level: str = "custom"
    pricing_policy_id: str | None = None
    default_headers: dict[str, Any] = Field(default_factory=dict)
    admin_id: str | None = None


class ModelCatalogUpdatePayload(_StrictContract):
    model_id: str | None = None
    display_name: str | None = None
    generation_api: GenerationAPI | None = None
    provider_name: str | None = None
    category: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    timeout_seconds: float | None = None
    max_retries: int | None = None
    trust_level: str | None = None
    pricing_policy_id: str | None = None
    default_headers: dict[str, Any] | None = None
    admin_id: str | None = None


class ModelCatalogHealthPayload(_StrictContract):
    status: str
    error_message: str | None = None


class ModelCapabilityAssessmentPayload(_StrictContract):
    """Internal command produced only by the explicit probe runner."""

    profile: ModelCapabilityProfile
    evidence: ModelCapabilityProbeEvidence
