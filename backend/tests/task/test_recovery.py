"""Tests for startup execution recovery reconciliation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.task.recovery as recovery


def _execution(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"exec-{status}",
        status=status,
        result_summary=None,
        error=None,
        last_error=None,
        completed_at=None,
        updated_at=None,
    )


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


@pytest.mark.asyncio
async def test_reconcile_interrupted_tasks_marks_active_executions_terminal():
    pending = _execution("pending")
    running = _execution("running")
    cancelling = _execution("cancelling")

    db = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarResult([pending, running, cancelling]))
    db.commit = AsyncMock()

    class _SessionCtx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with (
        patch.object(recovery.celery_settings, "enabled", True),
        patch("src.database.get_db_session", return_value=_SessionCtx()),
    ):
        reconciled = await recovery.reconcile_interrupted_tasks()

    assert reconciled == 3
    assert pending.status == "failed"
    assert running.status == "failed"
    assert cancelling.status == "cancelled"
    assert "process restart" in pending.last_error
    assert "process restart" in running.last_error
    assert "process restart" in cancelling.result_summary
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_interrupted_tasks_noops_when_nothing_active():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_ScalarResult([]))
    db.commit = AsyncMock()

    class _SessionCtx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with (
        patch.object(recovery.celery_settings, "enabled", True),
        patch("src.database.get_db_session", return_value=_SessionCtx()),
    ):
        reconciled = await recovery.reconcile_interrupted_tasks()

    assert reconciled == 0
    db.commit.assert_not_called()
