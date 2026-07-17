"""Tests for Celery queue isolation contracts."""

from __future__ import annotations

from src.task.celery_app import celery_app
from src.task.tasks.credit_periodic import process_credit_grant_rules  # noqa: F401


def test_periodic_credit_task_is_registered_and_routed() -> None:
    task_name = "credit_periodic.process_credit_grant_rules"

    assert task_name in celery_app.tasks
    assert celery_app.conf.task_routes[task_name]["queue"] == "default"
    assert celery_app.conf.beat_schedule["process-credit-grant-rules"]["task"] == task_name
