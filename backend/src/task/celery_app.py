"""Celery application configuration."""

from celery import Celery

from src.config.task_config import task_settings
from src.mission_runtime.contracts import MISSION_BROKER_VISIBILITY_TIMEOUT_SECONDS

MISSION_PREVIEW_CLEANUP_INTERVAL_SECONDS = 300.0

# Create Celery app
celery_app = Celery(
    "wenjin",
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
    broker_transport_options={
        "visibility_timeout": MISSION_BROKER_VISIBILITY_TIMEOUT_SECONDS,
    },
    result_backend_transport_options={
        "visibility_timeout": MISSION_BROKER_VISIBILITY_TIMEOUT_SECONDS,
    },

    # Task routing - route based on task type
    task_routes={
        "src.task.tasks.execute_task": {"queue": "default"},
        "src.task.tasks.process_chat_turn": {"queue": "default"},
        "src.task.tasks.reconcile_chat_turn_dispatches": {"queue": "default"},
        "src.task.tasks.drive_mission": {"queue": "long_running"},
        "src.task.tasks.reconcile_missions": {"queue": "default"},
        "src.task.tasks.cleanup_mission_previews": {"queue": "default"},
        "src.task.tasks.reconcile_thread_turn_billings": {"queue": "default"},
        "credit_periodic.process_credit_grant_rules": {"queue": "default"},
    },

    # Queue definitions
    task_queues={
        "default": {
            "exchange": "tasks",
            "routing_key": "task.default",
        },
        "long_running": {
            "exchange": "tasks",
            "routing_key": "task.long_running",
        },
        "priority": {
            "exchange": "tasks",
            "routing_key": "task.priority",
        },
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

# Beat schedule for periodic credit grant rules
celery_app.conf.beat_schedule = {
    **getattr(celery_app.conf, "beat_schedule", {}),
    "process-credit-grant-rules": {
        "task": "credit_periodic.process_credit_grant_rules",
        "schedule": 300.0,  # every 5 minutes
    },
    "reconcile-runnable-missions": {
        "task": "src.task.tasks.reconcile_missions",
        "schedule": 15.0,
    },
    "cleanup-expired-mission-previews": {
        "task": "src.task.tasks.cleanup_mission_previews",
        "schedule": MISSION_PREVIEW_CLEANUP_INTERVAL_SECONDS,
    },
    "reconcile-expired-thread-turn-billings": {
        "task": "src.task.tasks.reconcile_thread_turn_billings",
        "schedule": 60.0,
    },
    "reconcile-chat-turn-dispatches": {
        "task": "src.task.tasks.reconcile_chat_turn_dispatches",
        "schedule": 5.0,
    },
}
