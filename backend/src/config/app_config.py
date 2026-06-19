"""Application configuration using Pydantic Settings."""

import logging
import sys
import warnings
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _settings_config(env_prefix: str = "") -> SettingsConfigDict:
    """Create consistent settings config.

    Unit tests should not implicitly read a developer's local ``.env`` file,
    otherwise test results change based on machine-specific configuration.
    """
    env_file = None if "pytest" in sys.modules else ".env"
    return SettingsConfigDict(
        env_prefix=env_prefix,
        case_sensitive=False,
        env_file=env_file,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class JWTSettings(BaseSettings):
    """JWT authentication settings."""

    enabled: bool = Field(default=True, description="Enable JWT authentication")
    secret_key: str = Field(
        default="change-me-in-production",
        description="JWT secret key - use python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )
    algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440, description="Access token expiration in minutes")
    refresh_token_expire_days: int = Field(default=30, ge=1, le=365, description="Refresh token expiration in days")

    model_config = _settings_config("JWT_")

    @model_validator(mode="after")
    def validate_secret_key(self) -> "JWTSettings":
        """Validate that the JWT secret key is not the default value in production."""
        if self.secret_key == "change-me-in-production":
            warnings.warn(
                "JWT_SECRET_KEY is using the default value 'change-me-in-production'. "
                "This is insecure for production environments. "
                "Set a secure secret using: python -c \"import secrets; print(secrets.token_urlsafe(64))\"",
                stacklevel=2,
            )
            logger.warning(
                "JWT secret key is using default value. Set JWT_SECRET_KEY environment variable for production."
            )
        return self


class RedisSettings(BaseSettings):
    """Redis configuration."""

    enabled: bool = Field(default=False, description="Enable Redis")
    url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    max_connections: int = Field(default=20, ge=1, le=100, description="Max connection pool size")
    stream_max_connections: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Dedicated max connection pool size for SSE/pubsub streams",
    )
    socket_timeout_seconds: float = Field(
        default=2.0,
        ge=0.1,
        le=30.0,
        description="Redis socket read/write timeout in seconds",
    )
    stream_socket_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=120.0,
        description="Redis stream/pubsub socket read timeout in seconds",
    )
    socket_connect_timeout_seconds: float = Field(
        default=2.0,
        ge=0.1,
        le=30.0,
        description="Redis socket connect timeout in seconds",
    )
    rate_limit_redis_timeout_seconds: float = Field(
        default=0.25,
        ge=0.05,
        le=5.0,
        description="Rate-limit middleware Redis operation timeout in seconds",
    )

    # Cache TTL (seconds)
    llm_cache_ttl: int = Field(default=3600, ge=60, description="LLM response cache TTL")
    pdf_cache_ttl: int = Field(default=7200, ge=60, description="PDF parse cache TTL")
    session_cache_ttl: int = Field(default=86400, ge=60, description="Session cache TTL")

    # Rate limiting
    rate_limit_requests: int = Field(default=120, ge=1, description="Rate limit: requests per window")
    rate_limit_window: int = Field(default=60, ge=1, description="Rate limit: window in seconds")
    generation_lock_ttl: int = Field(default=600, ge=60, description="Generation lock TTL")

    model_config = _settings_config("REDIS_")


class CelerySettings(BaseSettings):
    """Celery async task configuration."""

    enabled: bool = Field(default=False, description="Enable Celery")
    broker_url: str = Field(default="redis://localhost:6379/1", description="Celery broker URL")
    result_backend: str = Field(default="redis://localhost:6379/2", description="Celery result backend URL")
    worker_concurrency: int = Field(default=2, ge=1, le=16, description="Worker concurrency")
    worker_pool: str = Field(
        default="solo",
        description="Celery worker pool implementation (solo or prefork)",
    )
    task_soft_time_limit: int = Field(default=600, ge=60, description="Soft time limit (triggers exception)")
    task_time_limit: int = Field(default=900, ge=60, description="Hard time limit (force terminate)")

    model_config = _settings_config("CELERY_")


class SentrySettings(BaseSettings):
    """Sentry error monitoring configuration."""

    enabled: bool = Field(default=False, description="Enable Sentry")
    dsn: str = Field(default="", description="Sentry DSN")
    environment: str = Field(default="production", description="Sentry environment")
    traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0, description="Traces sample rate")
    profiles_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0, description="Profiles sample rate")

    model_config = _settings_config("SENTRY_")


class PrometheusSettings(BaseSettings):
    """Prometheus monitoring configuration."""

    enabled: bool = Field(default=False, description="Enable Prometheus metrics")
    worker_port: int = Field(
        default=9153,
        ge=1,
        le=65535,
        description="HTTP port exposed by the Celery worker metrics server",
    )
    multiproc_dir: str = Field(
        default="",
        description="Directory used for Prometheus multiprocess worker metrics",
    )

    model_config = _settings_config("PROMETHEUS_")


class DataServiceSettings(BaseSettings):
    """Standalone DataService configuration."""

    url: str = Field(
        default="http://localhost:8080",
        description="Base URL used by backend services to call DataService",
    )
    internal_token: str = Field(
        default="change-me-in-production",
        description="Shared token for internal DataService calls",
    )
    timeout_seconds: float = Field(
        default=10.0,
        ge=0.1,
        le=120.0,
        description="HTTP timeout for DataService client calls",
    )

    model_config = _settings_config("DATASERVICE_")


class SMTPSettings(BaseSettings):
    """SMTP mail service configuration."""

    enabled: bool = Field(default=False, description="Enable SMTP email service")
    host: str = Field(default="smtp.example.com", description="SMTP server host")
    port: int = Field(default=465, ge=1, le=65535, description="SMTP port")
    username: str = Field(default="", description="Sender email address")
    password: str = Field(default="", description="SMTP authorization code/password")
    use_tls: bool = Field(default=True, description="Use TLS encryption")
    sender_name: str = Field(default="问津 Wenjin", description="Sender display name")

    # Verification code config
    code_length: int = Field(default=6, ge=4, le=10, description="Verification code length")
    code_ttl: int = Field(default=600, ge=60, le=3600, description="Verification code validity (seconds)")
    send_interval: int = Field(default=60, ge=10, le=600, description="Minimum send interval (seconds)")
    daily_limit: int = Field(default=10, ge=1, le=100, description="Daily send limit per email")

    model_config = _settings_config("SMTP_")


class LayoutParsingSettings(BaseSettings):
    """Layout parsing upload preprocessor settings."""

    enabled: bool = Field(default=False, description="Enable layout parsing preprocessor")
    api_url: str = Field(default="", description="Layout parsing API URL")
    token: str = Field(default="", description="Layout parsing API token")
    timeout_seconds: float = Field(
        default=120.0,
        ge=1.0,
        le=600.0,
        description="Layout parsing API timeout in seconds",
    )
    use_doc_orientation_classify: bool = Field(
        default=False,
        description="Enable document orientation classification",
    )
    use_doc_unwarping: bool = Field(
        default=False,
        description="Enable document unwarping",
    )
    use_chart_recognition: bool = Field(
        default=False,
        description="Enable chart recognition",
    )
    # Extended layout parsing options
    use_layout_detection: bool = Field(
        default=True,
        description="Enable layout region detection and sorting",
    )
    layout_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Layout model score threshold",
    )
    layout_nms: bool = Field(
        default=True,
        description="Enable NMS post-processing for layout detection",
    )
    restructure_pages: bool = Field(
        default=False,
        description="Restructure multi-page PDF results",
    )
    merge_tables: bool = Field(
        default=True,
        description="Merge cross-page tables",
    )
    relevel_titles: bool = Field(
        default=True,
        description="Recognize paragraph title levels",
    )
    prettify_markdown: bool = Field(
        default=True,
        description="Output prettified Markdown",
    )
    visualize: bool | None = Field(
        default=None,
        description="Return visualization images (null=use server config)",
    )

    model_config = _settings_config("LAYOUT_PARSING_")


class AppConfig(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = _settings_config()

    # CORS configuration - expects comma-separated string like "http://localhost:3000,https://example.com"
    cors_origins_str: str = Field(
        default="http://localhost:3000",
        description="Allowed CORS origins (comma-separated)",
        alias="CORS_ORIGINS",
    )

    # API Keys (fallback for simple setups)
    openai_api_key: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins_str.split(",") if origin.strip()]
    anthropic_api_key: str | None = None
    deepseek_api_key: str | None = None
    semantic_scholar_api_key: str | None = None
    semantic_scholar_rate_limit_delay: float = Field(
        default=1.0,
        alias="SEMANTIC_SCHOLAR_RATE_LIMIT_DELAY",
        ge=0.0,
        le=60.0,
        description="Minimum delay between Semantic Scholar API requests in seconds",
    )

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/wenjin"

    # Application
    environment: str = Field(default="development", description="Running environment")
    debug: bool = Field(default=False, description="Debug mode")
    e2e_test_hooks_enabled: bool = Field(
        default=False,
        alias="E2E_TEST_HOOKS_ENABLED",
        description="Enable unauthenticated Playwright-only test hook routes and scripted LLM queue.",
    )
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")
    gateway_event_loop_watchdog_enabled: bool = Field(
        default=True,
        alias="GATEWAY_EVENT_LOOP_WATCHDOG_ENABLED",
        description="Enable event loop lag watchdog for gateway self-healing",
    )
    gateway_event_loop_watchdog_interval_seconds: float = Field(
        default=2.0,
        alias="GATEWAY_EVENT_LOOP_WATCHDOG_INTERVAL_SECONDS",
        ge=0.5,
        le=30.0,
        description="Watchdog sampling interval in seconds",
    )
    gateway_event_loop_watchdog_lag_threshold_seconds: float = Field(
        default=20.0,
        alias="GATEWAY_EVENT_LOOP_WATCHDOG_LAG_THRESHOLD_SECONDS",
        ge=1.0,
        le=300.0,
        description="Lag threshold for considering the event loop blocked",
    )
    gateway_event_loop_watchdog_max_breaches: int = Field(
        default=2,
        alias="GATEWAY_EVENT_LOOP_WATCHDOG_MAX_BREACHES",
        ge=1,
        le=20,
        description="Consecutive lag breaches before forcing process exit",
    )
    runtime_run_recovery_limit: int = Field(
        default=300,
        alias="RUNTIME_RUN_RECOVERY_LIMIT",
        ge=10,
        le=5000,
        description="Maximum recent runs hydrated from Redis on gateway startup",
    )
    runtime_run_ttl_seconds: int = Field(
        default=86400,
        alias="RUNTIME_RUN_TTL_SECONDS",
        ge=300,
        le=604800,
        description="Run metadata retention in Redis (seconds)",
    )
    runtime_disconnect_cancel_grace_seconds: float = Field(
        default=1.5,
        alias="RUNTIME_DISCONNECT_CANCEL_GRACE_SECONDS",
        ge=0.0,
        le=30.0,
        description="Grace delay before canceling a disconnected run stream",
    )
    mcp_required_for_readiness: bool = Field(
        default=False,
        alias="MCP_REQUIRED_FOR_READINESS",
        description="Treat MCP runtime/tool health as a hard readiness dependency",
    )
    mcp_required_for_worker_bootstrap: bool = Field(
        default=False,
        alias="MCP_REQUIRED_FOR_WORKER_BOOTSTRAP",
        description="Fail worker bootstrap when MCP runtime has load errors",
    )

    # Paths
    config_path: str | None = None
    skills_path: str = "./skills/public"

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: object) -> object:
        """Accept common environment-name values accidentally passed as DEBUG."""
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if normalized in {"release", "prod", "production", "stable"}:
            return False
        if normalized in {"dev", "development"}:
            return True
        return value


@lru_cache
def get_settings() -> AppConfig:
    """Get cached settings instance."""
    return AppConfig()


@lru_cache
def get_jwt_settings() -> JWTSettings:
    """Get cached JWT settings instance."""
    return JWTSettings()


@lru_cache
def get_redis_settings() -> RedisSettings:
    """Get cached Redis settings instance."""
    return RedisSettings()


@lru_cache
def get_celery_settings() -> CelerySettings:
    """Get cached Celery settings instance."""
    return CelerySettings()


@lru_cache
def get_sentry_settings() -> SentrySettings:
    """Get cached Sentry settings instance."""
    return SentrySettings()


@lru_cache
def get_prometheus_settings() -> PrometheusSettings:
    """Get cached Prometheus settings instance."""
    return PrometheusSettings()


@lru_cache
def get_dataservice_settings() -> DataServiceSettings:
    """Get cached DataService settings instance."""
    return DataServiceSettings()


@lru_cache
def get_smtp_settings() -> SMTPSettings:
    """Get cached SMTP settings instance."""
    return SMTPSettings()


class ImageVLMSettings(BaseSettings):
    """Image VLM upload preprocessor settings."""

    enabled: bool = Field(default=False, description="Enable image VLM preprocessor")
    api_url: str = Field(default="", description="VLM API base URL (OpenAI-compatible)")
    token: str = Field(default="", description="VLM API token")
    model: str = Field(default="qwen2.5-vl-7b-instruct", description="VLM model name")
    timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=300.0,
        description="VLM API timeout in seconds",
    )
    prompt: str = Field(
        default="请详细描述这张图片的内容。如果是图表，请说明数据趋势和关键数值；如果是文字截图，请提取主要文字内容；如果是照片，请描述场景和主体。",
        description="System prompt for image understanding",
    )
    max_tokens: int = Field(
        default=2048,
        ge=256,
        le=8192,
        description="Max tokens for VLM response",
    )
    temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )

    model_config = _settings_config("IMAGE_VLM_")


@lru_cache
def get_layout_parsing_settings() -> LayoutParsingSettings:
    """Get cached layout parsing settings instance."""
    return LayoutParsingSettings()


@lru_cache
def get_image_vlm_settings() -> ImageVLMSettings:
    """Get cached image VLM settings instance."""
    return ImageVLMSettings()


# Convenience instances (backward compatible)
settings = get_settings()
jwt_settings = get_jwt_settings()
redis_settings = get_redis_settings()
celery_settings = get_celery_settings()
sentry_settings = get_sentry_settings()
prometheus_settings = get_prometheus_settings()
dataservice_settings = get_dataservice_settings()
smtp_settings = get_smtp_settings()
layout_parsing_settings = get_layout_parsing_settings()
image_vlm_settings = get_image_vlm_settings()
