"""Tests for startup execution recovery reconciliation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.task.recovery as recovery


@pytest.mark.asyncio
async def test_reconcile_interrupted_tasks_marks_active_executions_terminal():
    db = MagicMock()

    class _SessionCtx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _ExecutionService:
        def __init__(self, session) -> None:
            assert session is db
            self.reconcile_interrupted_executions = AsyncMock(return_value=3)

    with (
        patch.object(recovery.celery_settings, "enabled", True),
        patch("src.database.get_db_session", return_value=_SessionCtx()),
        patch("src.services.execution_service.ExecutionService", _ExecutionService),
    ):
        reconciled = await recovery.reconcile_interrupted_tasks()

    assert reconciled == 3


@pytest.mark.asyncio
async def test_reconcile_interrupted_tasks_noops_when_nothing_active():
    db = MagicMock()

    class _SessionCtx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _ExecutionService:
        def __init__(self, session) -> None:
            assert session is db
            self.reconcile_interrupted_executions = AsyncMock(return_value=0)

    with (
        patch.object(recovery.celery_settings, "enabled", True),
        patch("src.database.get_db_session", return_value=_SessionCtx()),
        patch("src.services.execution_service.ExecutionService", _ExecutionService),
    ):
        reconciled = await recovery.reconcile_interrupted_tasks()

    assert reconciled == 0
