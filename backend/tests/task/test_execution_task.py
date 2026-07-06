"""Tests for execution worker task guards."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.task.tasks.execution import (
    _execution_worker_id,
    _run_with_execution_lease_heartbeat,
    is_terminal_execution_status,
)


def test_failed_execution_status_is_terminal_for_worker_redelivery():
    assert is_terminal_execution_status("failed")
    assert is_terminal_execution_status("completed")
    assert is_terminal_execution_status("cancelled")
    assert not is_terminal_execution_status("running")


def test_execution_worker_id_uses_celery_request_id() -> None:
    task = SimpleNamespace(request=SimpleNamespace(id="worker-task-id-1234567890"))

    assert _execution_worker_id(task, "exec-1") == "worker-task-id-1234567890"


def test_execution_worker_id_falls_back_to_execution_id() -> None:
    task = SimpleNamespace(request=SimpleNamespace(id=None))

    assert _execution_worker_id(task, "exec-1234567890") == "exec-1234567890"


@pytest.mark.asyncio
async def test_run_with_execution_lease_heartbeat_returns_runner_result() -> None:
    class FakeExecutionService:
        def __init__(self) -> None:
            self.heartbeats = 0

        async def heartbeat_execution_lease(self, **kwargs):
            assert kwargs["execution_id"] == "exec-1"
            assert kwargs["worker_id"] == "worker-1"
            self.heartbeats += 1
            return {"status": "heartbeat"}

    async def _runner() -> str:
        await _short_sleep()
        return "done"

    service = FakeExecutionService()

    result = await _run_with_execution_lease_heartbeat(
        _runner(),
        execution_service=service,
        execution_id="exec-1",
        worker_id="worker-1",
        interval_seconds=0.001,
        ttl_seconds=10,
    )

    assert result == "done"
    assert service.heartbeats >= 1


@pytest.mark.asyncio
async def test_run_with_execution_lease_heartbeat_cancels_runner_when_lease_lost() -> None:
    cancelled = False

    class FakeExecutionService:
        async def heartbeat_execution_lease(self, **kwargs):
            _ = kwargs
            return {"status": "owner_mismatch"}

    async def _runner() -> None:
        nonlocal cancelled
        try:
            await _long_sleep()
        except asyncio.CancelledError:
            cancelled = True
            raise

    with pytest.raises(RuntimeError, match="owner_mismatch"):
        await _run_with_execution_lease_heartbeat(
            _runner(),
            execution_service=FakeExecutionService(),
            execution_id="exec-1",
            worker_id="worker-1",
            interval_seconds=0.001,
            ttl_seconds=10,
        )

    assert cancelled


async def _short_sleep() -> None:
    await asyncio.sleep(0.005)


async def _long_sleep() -> None:
    await asyncio.sleep(60)
