"""Task system configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TaskSettings(BaseSettings):
    """Celery and task system settings."""

    # Celery
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1", description="Celery broker URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2", description="Celery result backend URL"
    )

    # Worker
    worker_concurrency: int = Field(default=4, ge=1, description="Worker concurrency")
    worker_prefetch_multiplier: int = Field(
        default=2, ge=1, description="Worker prefetch multiplier"
    )

    # Task defaults
    task_soft_time_limit: int = Field(
        default=600, ge=60, description="Soft time limit in seconds (10 minutes)"
    )
    task_time_limit: int = Field(
        default=900, ge=60, description="Hard time limit in seconds (15 minutes)"
    )
    task_acks_late: bool = Field(default=True, description="Acknowledge tasks after completion")

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

    model_config = SettingsConfigDict(
        env_prefix="TASK_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Global instance
task_settings = TaskSettings()
