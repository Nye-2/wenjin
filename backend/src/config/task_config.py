"""Task system configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config.app_config import celery_settings, root_env_file


def _task_settings_config() -> SettingsConfigDict:
    """Create task settings config without leaking local `.env` into tests."""
    return SettingsConfigDict(
        env_prefix="TASK_",
        case_sensitive=False,
        env_file=root_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


class TaskSettings(BaseSettings):
    """Celery and task system settings."""

    # Celery
    celery_broker_url: str = Field(
        default_factory=lambda: celery_settings.broker_url,
        description="Celery broker URL",
    )
    celery_result_backend: str = Field(
        default_factory=lambda: celery_settings.result_backend,
        description="Celery result backend URL",
    )

    # Worker
    worker_concurrency: int = Field(
        default_factory=lambda: celery_settings.worker_concurrency,
        ge=1,
        description="Worker concurrency",
    )
    worker_prefetch_multiplier: int = Field(
        default=2, ge=1, description="Worker prefetch multiplier"
    )

    # Task defaults
    task_soft_time_limit: int = Field(
        default_factory=lambda: celery_settings.task_soft_time_limit,
        ge=60,
        description="Soft time limit in seconds (10 minutes)",
    )
    task_time_limit: int = Field(
        default_factory=lambda: celery_settings.task_time_limit,
        ge=60,
        description="Hard time limit in seconds (15 minutes)",
    )
    task_acks_late: bool = Field(default=True, description="Acknowledge tasks after completion")
    task_default_retry_delay: int = Field(
        default=60, ge=1, description="Default retry delay in seconds"
    )

    # Progress
    progress_update_interval: int = Field(
        default=2, ge=1, description="Progress update interval in seconds"
    )

    # Storage
    task_redis_ttl: int = Field(
        default=86400, ge=60, description="Task Redis TTL in seconds (24 hours)"
    )

    # Rate limits
    max_concurrent_tasks_per_user: int = Field(
        default=3, ge=1, description="Max concurrent tasks per user"
    )
    max_priority_for_non_admin: int = Field(
        default=7, ge=1, le=10, description="Max priority for non-admin users"
    )

    model_config = _task_settings_config()


# Global instance
task_settings = TaskSettings()
