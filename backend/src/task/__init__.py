"""Async task system package."""

from src.task.celery_app import celery_app

__all__ = ["celery_app"]
