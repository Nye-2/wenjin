"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional, List
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


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

    model_config = SettingsConfigDict(
        env_prefix="JWT_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class SMTPSettings(BaseSettings):
    """SMTP mail service configuration."""

    enabled: bool = Field(default=False, description="Enable SMTP email service")
    host: str = Field(default="smtp.example.com", description="SMTP server host")
    port: int = Field(default=465, ge=1, le=65535, description="SMTP port")
    username: str = Field(default="", description="Sender email address")
    password: str = Field(default="", description="SMTP authorization code/password")
    use_tls: bool = Field(default=True, description="Use TLS encryption")
    sender_name: str = Field(default="Academiagpt", description="Sender display name")

    # Verification code config
    code_length: int = Field(default=8, ge=6, le=10, description="verification code length")
    code_ttl: int = Field(default=600, ge=60, le=600, description="verification code validity (seconds)")
    send_interval: int = Field(default=60, ge=10, le=600, description="minimum send interval (seconds)")
    daily_limit: int = Field(default=10, ge=1, le=10, description="daily send limit")

    model_config = SettingsConfigDict(
        env_prefix="SMTP_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AppConfig(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    semantic_scholar_api_key: Optional[str] = None

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/academiagpt"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Application
    debug: bool = False
    log_level: str = "INFO"

    # Paths
    config_path: Optional[str] = None
    skills_path: str = "./skills/public"


@lru_cache
def get_settings() -> AppConfig:
    """Get cached settings instance."""
    return AppConfig()


# Convenience instances
settings = get_settings()
jwt_settings = JWTSettings()
smtp_settings = SMTPSettings()
