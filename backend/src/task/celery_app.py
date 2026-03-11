"""Celery application configuration."""

from celery import Celery

from src.config.task_config import task_settings

# Create Celery app
celery_app = Celery(
    "academiagpt",
    broker=task_settings.celery_broker_url,
    backend=task_settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Worker settings
    worker_concurrency=task_settings.worker_concurrency,
    worker_prefetch_multiplier=task_settings.worker_prefetch_multiplier,

    # Task execution
    task_acks_late=task_settings.task_acks_late,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=task_settings.task_soft_time_limit,
    task_time_limit=task_settings.task_time_limit,

    # Result settings
    result_expires=task_settings.task_redis_ttl,

    # Task routing
    task_routes={
        "src.task.tasks.*": {"queue": "default"},
    },

    # Default queue
    task_default_queue="default",
    task_default_exchange="tasks",
    task_default_routing_key="task.default",
)

# Auto-discover tasks from registered modules
celery_app.autodiscover_tasks([
    "src.task.tasks",
])
