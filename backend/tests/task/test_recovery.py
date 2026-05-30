"""Tests for startup execution recovery reconciliation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import src.task.recovery as recovery


@pytest.mark.asyncio
async def test_reconcile_interrupted_tasks_marks_active_executions_terminal():
    class _ExecutionService:
        def __init__(self) -> None:
            self.reconcile_interrupted_executions = AsyncMock(return_value=3)

    with (
        patch.object(recovery.celery_settings, "enabled", True),
        patch("src.services.execution_service.ExecutionService", _ExecutionService),
    ):
        reconciled = await recovery.reconcile_interrupted_tasks()

    assert reconciled == 3


@pytest.mark.asyncio
async def test_reconcile_interrupted_tasks_noops_when_nothing_active():
    class _ExecutionService:
        def __init__(self) -> None:
            self.reconcile_interrupted_executions = AsyncMock(return_value=0)

    with (
        patch.object(recovery.celery_settings, "enabled", True),
        patch("src.services.execution_service.ExecutionService", _ExecutionService),
    ):
        reconciled = await recovery.reconcile_interrupted_tasks()

    assert reconciled == 0
