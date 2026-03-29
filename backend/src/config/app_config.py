"""Application configuration using Pydantic Settings."""

import logging
import sys
import warnings
from functools import lru_cache

from pydantic import Field, model_validator
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

    # Cache TTL (seconds)
    llm_cache_ttl: int = Field(default=3600, ge=60, description="LLM response cache TTL")
    pdf_cache_ttl: int = Field(default=7200, ge=60, description="PDF parse cache TTL")
    session_cache_ttl: int = Field(default=86400, ge=60, description="Session cache TTL")

    # Rate limiting
    rate_limit_requests: int = Field(default=30, ge=1, description="Rate limit: requests per window")
    rate_limit_window: int = Field(default=60, ge=1, description="Rate limit: window in seconds")
    generation_lock_ttl: int = Field(default=600, ge=60, description="Generation lock TTL")

    model_config = _settings_config("REDIS_")


class CelerySettings(BaseSettings):
    """Celery async task configuration."""

    enabled: bool = Field(default=False, description="Enable Celery")
    broker_url: str = Field(default="redis://localhost:6379/1", description="Celery broker URL")
    result_backend: str = Field(default="redis://localhost:6379/2", description="Celery result backend URL")
    worker_concurrency: int = Field(default=2, ge=1, le=16, description="Worker concurrency")
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

    model_config = _settings_config("PROMETHEUS_")


class SMTPSettings(BaseSettings):
    """SMTP mail service configuration."""

    enabled: bool = Field(default=False, description="Enable SMTP email service")
    host: str = Field(default="smtp.example.com", description="SMTP server host")
    port: int = Field(default=465, ge=1, le=65535, description="SMTP port")
    username: str = Field(default="", description="Sender email address")
    password: str = Field(default="", description="SMTP authorization code/password")
    use_tls: bool = Field(default=True, description="Use TLS encryption")
    sender_name: str = Field(default="观澜 Guanlan", description="Sender display name")

    # Verification code config
    code_length: int = Field(default=6, ge=4, le=10, description="Verification code length")
    code_ttl: int = Field(default=600, ge=60, le=3600, description="Verification code validity (seconds)")
    send_interval: int = Field(default=60, ge=10, le=600, description="Minimum send interval (seconds)")
    daily_limit: int = Field(default=10, ge=1, le=100, description="Daily send limit per email")

    model_config = _settings_config("SMTP_")


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

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/academiagpt"

    # Application
    environment: str = Field(default="development", description="Running environment")
    debug: bool = Field(default=False, description="Debug mode")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    log_level: str = Field(default="INFO", description="Logging level")

    # Paths
    config_path: str | None = None
    skills_path: str = "./skills/public"


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
def get_smtp_settings() -> SMTPSettings:
    """Get cached SMTP settings instance."""
    return SMTPSettings()


# Convenience instances (backward compatible)
settings = get_settings()
jwt_settings = get_jwt_settings()
redis_settings = get_redis_settings()
celery_settings = get_celery_settings()
sentry_settings = get_sentry_settings()
prometheus_settings = get_prometheus_settings()
smtp_settings = get_smtp_settings()
