"""Admin-managed model catalog entries."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class ModelProviderProtocol(StrEnum):
    """Supported model provider protocols."""

    OPENAI_COMPATIBLE = "openai_compatible"


class ModelCategory(StrEnum):
    """Model catalog categories exposed to routing."""

    LLM = "llm"


class ModelTrustLevel(StrEnum):
    """Trust level for model providers."""

    TRUSTED = "trusted"
    CUSTOM = "custom"


class ModelHealthStatus(StrEnum):
    """Connection health status for a model catalog entry."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    FAILED = "failed"


class ModelCatalogEntry(Base, UUIDMixin, TimestampMixin):
    """DataService-owned runtime model configuration."""

    __tablename__ = "model_catalog_entries"
    __table_args__ = (
        Index("ix_model_catalog_enabled_category", "enabled", "category"),
        Index("ix_model_catalog_default_category", "is_default", "category"),
        Index("ix_model_catalog_health_status", "health_status"),
    )

    model_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_protocol: Mapped[ModelProviderProtocol] = mapped_column(
        SQLEnum(
            ModelProviderProtocol,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="model_provider_protocol",
        ),
        nullable=False,
        default=ModelProviderProtocol.OPENAI_COMPATIBLE,
        server_default=ModelProviderProtocol.OPENAI_COMPATIBLE.value,
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Custom", server_default="Custom")
    category: Mapped[ModelCategory] = mapped_column(
        SQLEnum(
            ModelCategory,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="model_category",
        ),
        nullable=False,
        default=ModelCategory.LLM,
        server_default=ModelCategory.LLM.value,
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_last4: Mapped[str | None] = mapped_column(String(16), nullable=True)
    api_key_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    supports_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    supports_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    supports_json_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    supports_json_schema: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    supports_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    supports_reasoning_effort: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096, server_default="4096")
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7, server_default="0.7")
    timeout_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_retries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trust_level: Mapped[ModelTrustLevel] = mapped_column(
        SQLEnum(
            ModelTrustLevel,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="model_trust_level",
        ),
        nullable=False,
        default=ModelTrustLevel.CUSTOM,
        server_default=ModelTrustLevel.CUSTOM.value,
    )
    pricing_policy_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    health_status: Mapped[ModelHealthStatus] = mapped_column(
        SQLEnum(
            ModelHealthStatus,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="model_health_status",
        ),
        nullable=False,
        default=ModelHealthStatus.UNKNOWN,
        server_default=ModelHealthStatus.UNKNOWN.value,
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_headers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_by_admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by_admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:
        return f"<ModelCatalogEntry(model_id={self.model_id!r}, enabled={self.enabled!r})>"
