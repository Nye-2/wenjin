"""Model catalog domain contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ModelCatalogRecord(BaseModel):
    """Admin-safe model catalog projection."""

    id: str | None = None
    model_id: str
    display_name: str
    provider_protocol: str
    provider_name: str
    category: str
    model_name: str
    base_url: str
    api_key_redacted: str | None = None
    enabled: bool = True
    is_default: bool = False
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_json_mode: bool = True
    supports_json_schema: bool = False
    supports_vision: bool = False
    supports_reasoning_effort: bool = False
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


class ModelRuntimeConfig(BaseModel):
    """Internal runtime model configuration with decrypted secret."""

    model_id: str
    display_name: str
    provider_protocol: str
    provider_name: str
    category: str
    model_name: str
    base_url: str
    api_key: str
    is_default: bool = False
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_json_mode: bool = True
    supports_json_schema: bool = False
    supports_vision: bool = False
    supports_reasoning_effort: bool = False
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: float | None = None
    max_retries: int | None = None
    trust_level: str = "custom"
    pricing_policy_id: str | None = None
    config_version: int = 1
    default_headers: dict[str, Any] = Field(default_factory=dict)
