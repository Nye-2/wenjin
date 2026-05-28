"""Tests for Celery queue isolation contracts."""

from __future__ import annotations

from src.task.celery_app import celery_app


def test_memory_capture_routes_to_dedicated_queue():
    assert celery_app.conf.task_routes["src.task.tasks.capture_memory"]["queue"] == "memory"
    assert "memory" in celery_app.conf.task_queues
